"""Prompt Chain Generator — 生成多阶段 Claude Code 提示词。

Public API:
    generator = PromptChainGenerator(project_root=".")
    report = generator.diagnose(files=["src/core/*.py"], feature_context="Multi-Agent Squad")
    prompts = generator.generate(feature="Multi-Agent Squad", diagnosis=report, output_dir="./prompts")
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DiagnosisReport:
    """Phase 0 扇出诊断输出。

    Attributes:
        files_read: 实际读取的文件路径列表（glob 展开后）。
        problem_domains: 识别出的问题域，每项含 ``{name, severity, summary}``。
        modified_files: 需要修改的文件，每项含 ``{path, reason, priority}``，priority ∈ P0/P1/P2。
        new_files: 需要新建的文件，每项含 ``{path, purpose}``。
        dependency_graph: 文件依赖关系的 Mermaid / 文本表示。
        risks: 已识别风险，每项含 ``{kind, detail, mitigation}``。
    """

    files_read: list[str] = field(default_factory=list)
    problem_domains: list[dict[str, Any]] = field(default_factory=list)
    modified_files: list[dict[str, Any]] = field(default_factory=list)
    new_files: list[dict[str, Any]] = field(default_factory=list)
    dependency_graph: str = ""
    risks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PhasePrompt:
    """单个阶段的提示词文件。

    Attributes:
        phase: 阶段编号（0-N，-1 为 final）。
        title: 阶段标题，如 "扇出诊断"。
        content: 渲染后的 Markdown 内容。
        output_path: 写入磁盘的绝对路径。
    """

    phase: int
    title: str
    content: str
    output_path: Path


class PromptChainGenerator:
    """为复杂功能生成多阶段 Claude Code Prompt Chain。

    用法::

        generator = PromptChainGenerator(project_root="/path/to/project")
        report = generator.diagnose(files=["src/core/*.py"])
        prompts = generator.generate(
            feature="Multi-Agent Squad 支持",
            diagnosis=report,
            output_dir="./prompts",
        )
    """

    # (phase, title, description)
    PHASES: tuple[tuple[int, str, str], ...] = (
        (0, "扇出诊断", "读取核心文件，输出问题清单和依赖关系"),
        (1, "核心数据模型", "实现语义分析引擎和核心数据模型"),
        (2, "编排组合层", "实现调度、组合、协作逻辑"),
        (3, "技能分配层", "实现 per-agent 技能选择和隔离"),
        (4, "集成串联", "串联所有模块，修改入口文件"),
        (5, "CLI 增强", "增强用户体验，添加交互输出"),
        (6, "端到端验证", "Linux 容器验证清单"),
    )

    def __init__(self, project_root: str | Path = ".") -> None:
        self.project_root = Path(project_root).resolve()

    # ── Phase 0: 扇出诊断 ─────────────────────────────────────────────────

    def diagnose(
        self,
        files: list[str],
        feature_context: str = "",
    ) -> DiagnosisReport:
        """扇出诊断：展开 glob、读取指定文件，返回结构化报告。

        Args:
            files: 文件路径或 glob 模式列表。
            feature_context: 当前功能上下文（影响问题域识别）。

        Returns:
            DiagnosisReport，``files_read`` 字段填充实际展开后的路径。
        """
        expanded = self._expand_globs(files)
        logger.info("扇出诊断 %d 个文件 (feature=%s)...", len(expanded), feature_context)

        return DiagnosisReport(
            files_read=expanded,
            problem_domains=[],
            modified_files=[],
            new_files=[],
            dependency_graph="",
            risks=[],
        )

    def _expand_globs(self, patterns: list[str]) -> list[str]:
        """展开 glob 模式，过滤目录、返回相对项目根的路径。

        Args:
            patterns: 形如 ``["src/core/*.py", "src/agent/*.py"]`` 的列表。

        Returns:
            去重后的相对路径列表，按字典序排序。
        """
        seen: set[str] = set()
        expanded: list[str] = []
        for pattern in patterns:
            pattern = pattern.strip()
            if not pattern:
                continue
            # 拒绝绝对路径外的遍历模式
            if ".." in pattern.split("/"):
                logger.warning("跳过含 .. 的路径: %s", pattern)
                continue
            for match in sorted(self.project_root.glob(pattern)):
                if not match.is_file():
                    continue
                rel = match.relative_to(self.project_root).as_posix()
                if rel not in seen:
                    seen.add(rel)
                    expanded.append(rel)
        return expanded

    # ── Phase 1-N: 生成提示词 ──────────────────────────────────────────────

    def generate(
        self,
        feature: str,
        diagnosis: DiagnosisReport | None = None,
        output_dir: str | Path = "./prompts",
    ) -> list[PhasePrompt]:
        """生成分阶段提示词文件。

        Args:
            feature: 功能名称，如 ``"Multi-Agent Squad"``。
            diagnosis: 诊断报告（可选）。为 None 时 Phase 0 用占位模板。
            output_dir: 输出目录，不存在则创建。

        Returns:
            生成的 :class:`PhasePrompt` 列表，按阶段升序。
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        generated: list[PhasePrompt] = []
        project_name = self._get_project_name()

        for phase_num, phase_title, phase_desc in self.PHASES:
            content = self._render_phase(
                phase=phase_num,
                title=phase_title,
                description=phase_desc,
                feature=feature,
                project_name=project_name,
                diagnosis=diagnosis,
            )

            slug = self._slugify(phase_title)
            if phase_num == 6:
                filename = "final-e2e-validation.md"
            elif slug:
                filename = f"phase-{phase_num}-{slug}.md"
            else:
                # 纯中文/空 slug → 用阶段编号兜底
                filename = f"phase-{phase_num}.md"
            filepath = output_path / filename
            filepath.write_text(content, encoding="utf-8")

            generated.append(
                PhasePrompt(
                    phase=phase_num,
                    title=phase_title,
                    content=content,
                    output_path=filepath,
                )
            )
            logger.info("已生成: %s", filepath)

        return generated

    # ── 渲染 ──────────────────────────────────────────────────────────────

    def _render_phase(
        self,
        phase: int,
        title: str,
        description: str,
        feature: str,
        project_name: str,
        diagnosis: DiagnosisReport | None,
    ) -> str:
        if phase == 0:
            return self._render_phase_0(project_name, feature, diagnosis)
        if phase == 6:
            return self._render_final_validation(project_name, feature)
        return self._render_phase_n(phase, title, description, project_name, feature)

    def _render_phase_0(
        self,
        project_name: str,
        feature: str,
        diagnosis: DiagnosisReport | None,
    ) -> str:
        files_rows = self._format_files_table(diagnosis)
        return f"""# {project_name} — Phase 0: 扇出诊断

> 目标功能: **{feature}**

请先执行以下步骤来全面理解项目：

## Step 1: 探索项目结构

读取以下关键文件来理解项目架构：

| 文件 | 阅读目的 |
|:---|:---|
{files_rows}

## Step 2: 识别核心问题

请识别当前实现中的以下问题：

- 现有架构中阻塞 {feature} 的耦合点
- 需要新增的接口与数据模型
- 涉及的现有测试是否需要更新

## Step 3: 输出分析报告

请输出以下内容（Markdown 列表形式）：

- 所有需要修改的文件（P0/P1/P2 分级）
- 所有需要新建的文件
- 文件间的依赖关系（建议执行顺序）
- 每项的工作量估计（S/M/L）

> 不要在此阶段写代码——只输出诊断结论。
"""

    def _render_phase_n(
        self,
        phase: int,
        title: str,
        desc: str,
        project_name: str,
        feature: str,
    ) -> str:
        prev_phase = phase - 1
        prev_titles = {p: t for p, t, _ in self.PHASES}
        prev_title = prev_titles.get(prev_phase, "")
        return f"""# {project_name} — Phase {phase}: {title}

## 前置条件

✅ Phase {prev_phase} 已完成 — {prev_title}

## 任务

{desc} — 实现 **{feature}** 的 {title} 层。

## 你必须先读的当前文件

| 文件 | 关键关注点 |
|:---|:---|
| _待填充_ | _待填充_ |

## 需求

### 子需求 1

_描述..._

### 子需求 2

_描述..._

## 关键实现要点

| 要点 | 实现方式 |
|:---|:---|
| _要点 1_ | _方式..._ |

## 验证标准

- [ ] 单元测试通过
- [ ] 类型检查通过 (`basedpyright`)
- [ ] 向后兼容（无破坏性 API 变更）

## 输出

请输出以下文件的完整内容：

1. `path/to/file.py`
2. `path/to/test_file.py`
"""

    def _render_final_validation(self, project_name: str, feature: str) -> str:
        return f"""# {project_name} — 最终验证: Linux 容器端到端测试

> 目标功能: **{feature}**

## 前置条件

✅ Phase 0-5 已完成

## 验证清单

### 环境

- 容器工具: orbstack → docker → lima（自动检测）
- 镜像: ubuntu:22.04
- 挂载项目到 `/app`

### 步骤

1. **安装依赖**: `apt-get install` + `uv sync` + `npm install -g @anthropic-ai/claude-code`
2. **构建 hook**: `vibe build claude-code --output ~/.claude`
3. **安装技能**: `vibe install mattpocock && vibe install superpowers`
4. **类型检查**: `npx basedpyright src/`
5. **单元测试**: `pytest tests/agent/ tests/core/ tests/cli/ -v`
6. **CLI 验证**: `vibe route` 5 种 InterceptionMode（SINGLE / SINGLE_AGENT / MULTI_AGENT_SQUAD / ORCHESTRATE / SLASH_COMMAND）
7. **Hook 验证**: `echo '{{"user_prompt":"...}}' | bash ~/.claude/hooks/vibesop-route.sh`

### 输出

JSON 格式验证报告，包含：

```json
{{
  "environment": {{ "container_tool": "...", "python": "..." }},
  "results": {{ "unit_tests": {{...}}, "cli_modes": {{...}}, "hook_path": {{...}} }},
  "p0_issues": [],
  "p1_issues": [],
  "conclusion": "✅ 验证通过"
}}
```

或直接调用：

```bash
vibe prompt-chain validate --json
```
"""

    # ── 辅助 ──────────────────────────────────────────────────────────────

    def _format_files_table(self, diagnosis: DiagnosisReport | None) -> str:
        """Render the diagnosis files_read list as Markdown table rows."""
        if not diagnosis or not diagnosis.files_read:
            return "| _（未指定文件，请由诊断者自行补充）_ | _待识别_ |"
        return "\n".join(f"| `{f}` | _待识别_ |" for f in diagnosis.files_read[:30])

    def _get_project_name(self) -> str:
        """从 pyproject.toml 读取 ``[project] name``，失败回退到目录名。"""
        pyproject = self.project_root / "pyproject.toml"
        if pyproject.exists():
            try:
                for line in pyproject.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped.startswith("name") and "=" in stripped:
                        # e.g. name = "vibesop"
                        _, _, raw = stripped.partition("=")
                        return raw.strip().strip('"').strip("'")
            except OSError:
                logger.debug("pyproject.toml 读取失败，回退到目录名")
        return self.project_root.name or "Project"

    @staticmethod
    def _slugify(text: str) -> str:
        """将中英混排标题转为文件名 slug（ASCII-only）。

        中文/特殊字符会被剔除；如果剩余 slug 为空（纯中文标题），
        调用方负责 fallback。返回值不含 ``-`` 前后缀。
        """
        # ASCII-only：\w 在默认模式下等价于 [a-zA-Z0-9_]
        text = text.lower().strip()
        text = re.sub(r"[^a-z0-9\s-]", "", text)
        text = re.sub(r"[\s_]+", "-", text)
        text = text.strip("-")
        return text[:50]
