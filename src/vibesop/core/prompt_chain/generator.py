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
            pattern_clean = pattern.strip()
            if not pattern_clean:
                continue
            # 拒绝绝对路径外的遍历模式
            if ".." in pattern_clean.split("/"):
                logger.warning("跳过含 .. 的路径: %s", pattern_clean)
                continue
            for match in sorted(self.project_root.glob(pattern_clean)):
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

## 验证目标

三层验证（缺一不可）：
1. **VibeSOP 自身** — CLI 路由 pipeline + skill index + 单元测试
2. **VibeSOP × Agent 配置生成** — hook 文件、settings.json、CLAUDE.md / AGENTS.md
3. **VibeSOP × Agent 真实集成** — hook 触发后返回有效的 skill 推荐（最易遗漏，必须验证）

## 验证清单

### A. 容器与依赖（必须按顺序，否则后续步骤失败）

容器：orbstack → docker → lima（自动检测）；镜像 `ubuntu:22.04`；挂载项目到 `/app`。

```bash
# A1. 创建容器
docker run -d --name vibesop-e2e --hostname vibesop-e2e \\
  -v $PWD:/app -w /app ubuntu:22.04 sleep infinity

# A2. apt 基础包（jq 必装 — hook 用 jq 解析 JSON envelope）
docker exec vibesop-e2e bash -c "apt-get update -qq && \\
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \\
  python3 python3-venv git curl npm ca-certificates gnupg build-essential jq zstd"

# A3. Node 20（Ubuntu 22.04 自带 Node 12 太旧，Claude Code 需 18+；
#     必须先 remove libnode-dev/libnode72/npm 否则 NodeSource 冲突）
docker exec vibesop-e2e bash -c "curl -fsSL https://deb.nodesource.com/setup_20.x | sh - && \\
  apt-get remove -y -qq libnode-dev libnode72 npm && apt-get install -y nodejs"

# A4. uv（自动下载 Python 3.12，无需 deadsnakes PPA）
docker exec vibesop-e2e bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh"

# A5. VibeSOP
docker exec -w /app vibesop-e2e bash -c "export PATH=/root/.local/bin:$PATH && uv sync"
```

### B. AI Agent 安装

```bash
# B1. Claude Code（npm）
docker exec vibesop-e2e npm install -g @anthropic-ai/claude-code
docker exec vibesop-e2e claude --version  # 期望：2.x.x

# B2. Kimi Code（官方 install.sh，ACP 协议）
docker exec vibesop-e2e bash -c \\
  "curl -fsSL https://code.kimi.com/kimi-code/install.sh -o /tmp/kimi-install.sh && \\
   bash /tmp/kimi-install.sh"
docker exec vibesop-e2e /root/.kimi-code/bin/kimi --version  # 期望：0.14+

# B3. Pi Agent：当前 npm 注册表无官方包，跳过实际安装，仅验证 vibe build pi 配置文件生成
```

### C. LLM Provider 配置（关键 — 不配置 indexer 100% 失败）

**选其一**：

```bash
# C1a. 方案一：宿主机 oMLX（OpenAI 兼容，端口 11434）
cat > /tmp/vibe-config.toml <<EOF
[llm]
provider = "openai"
model = "Qwen3.6-35B-A3B-mxfp8"
api_base = "http://host.docker.internal:11434/v1"
api_key = "local-omlx-fake-key-min-11-chars"
EOF
docker cp /tmp/vibe-config.toml vibesop-e2e:/root/.vibe/config.toml

# C1b. 方案二：DeepSeek API（速度更快，需要 host 提供 DEEPSEEK_API_KEY）
cat > /tmp/vibe-config.toml <<EOF
[llm]
provider = "deepseek"
model = "deepseek-v4-flash"
EOF
docker cp /tmp/vibe-config.toml vibesop-e2e:/root/.vibe/config.toml
# 后续命令必须 -e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY 透传
```

**已知坑**：
- 本地小模型（<7B，如 qwen2.5:0.5b/1.5b）无法产出 indexer 期望的结构化 JSON → `indexed_count` 永远为 0
- thinking-capable 模型（Qwen3.x、DeepSeek-R1、deepseek-v4-flash）需 `max_tokens>=4000`（v7.3.2 已修）

### D. Skill Index 构建（漏掉这步 → AI_TRIAGE 永远 "No embeddings in index"）

```bash
# D1. 安装技能包
docker exec -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && \\
   uv run vibe install mattpocock && uv run vibe install superpowers"

# D2. 构建 skill embedding index（vibe quickstart 交互式不易自动化，用 Python 直调）
docker exec -e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && uv run python -c \"
from vibesop.core.skills.indexer import SkillIndexer
from vibesop.core.llm_config import LLMConfigResolver
from vibesop.llm.factory import create_provider

resolver = LLMConfigResolver()
cfg = resolver.get_llm_for_understanding()
factory = lambda: create_provider(provider=cfg.provider, api_key=cfg.api_key, base_url=cfg.api_base)
idx = SkillIndexer(project_root='/app', llm_factory=factory)
result = idx.build_index(scope='global', show_progress=True, force=True, max_workers=4)
print(f'indexed: {{result.indexed_count}}/{{result.failed_count + result.indexed_count}}')
\""

# D3. 验证 index 非空
docker exec vibesop-e2e cat /root/.vibe/skill-index.json | \\
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(f'indexed: {{d.get(\"indexed_count\")}}'); assert d.get('indexed_count',0) > 0, 'INDEX EMPTY'"
```

### E. VibeSOP 配置生成（每个 Agent 都跑一遍）

```bash
docker exec -w /app vibesop-e2e bash -c "export PATH=/root/.local/bin:$PATH && \\
  uv run vibe build claude-code --output /root/.claude && \\
  uv run vibe build kimi-cli --output /root/.kimi-code && \\
  uv run vibe build pi --output /app/.pi"
```

### F. CLI 路由验证（5 种 InterceptionMode）

```bash
# F1. SINGLE — 短查询，AI_TRIAGE 应选中具体技能
docker exec -e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && uv run vibe route '帮我调试 TypeError NoneType 错误' --yes"
# 期望：Selected: <skill_id> (confidence > 60%)，不是 FALLBACK_LLM

# F2. ORCHESTRATE — 长语义，多步分解
docker exec -e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && uv run vibe route '请设计一个高可用的微服务架构，包括服务拆分、API 网关和监控方案' --yes"
# 期望：Steps: >=2，每个 Step 有 skill_id（不是全 fallback-llm）

# F3. MULTI_AGENT_SQUAD — 多角色
docker exec -e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && uv run vibe route '设计微服务架构、用Python实现核心模块、做安全审查' --yes"
# 期望：Agent Squad（architect/implementer/reviewer/red_team）

# F4. SLASH_COMMAND
docker exec -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && uv run vibe route '/vibe-list' --yes"
# 期望：列出已安装技能

# F5. EXPLICIT（@skill_id 语法）
docker exec -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && uv run vibe route '@builtin/instinct 学习最近的会话' --yes"
```

### G. Hook 集成验证（最关键，最易出问题）

```bash
# G1. 文件存在性
docker exec vibesop-e2e ls -la /root/.claude/hooks/  # 应有 vibesop-route.sh + vibesop-track.sh
docker exec vibesop-e2e cat /root/.claude/settings.json  # UserPromptSubmit hook 已注册

# G2. CLAUDE.md 协议注入
docker exec vibesop-e2e grep "Routing is automatic" /root/.claude/CLAUDE.md

# G3. Hook JSON envelope 解析（关键 — Round 2 修过 P1 bug）
# 正确字段名是 .prompt（不是 .user_prompt）
echo '{{"prompt":"帮我调试 TypeError NoneType 错误","session_id":"test","cwd":"/app","hook_event_name":"UserPromptSubmit","transcript_path":"/tmp/x.jsonl"}}' | \\
  docker exec -e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY -i vibesop-e2e /root/.claude/hooks/vibesop-route.sh

# G4. 必须验证：hook 返回的 additionalContext 包含 skill_id（不只是 hook 能跑）
# 上述命令的输出应包含：
#   "additionalContext": "..." 中含 "skill_id": "<具体技能>"
# 如果是 "No matching skill found" → AgentRuntime 路径有 P0 bug，需修
```

### H. 类型检查 + 单元测试

```bash
# H1. basedpyright
docker exec -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && uv run --extra dev basedpyright src/ 2>&1 | tail -3"
# 期望：0 errors（warnings OK）

# H2. 单元测试
docker exec -w /app vibesop-e2e bash -c \\
  "export PATH=/root/.local/bin:$PATH && \\
   uv run pytest tests/core/orchestration/ tests/agent/runtime/ tests/cli/ -q --no-cov"
# 期望：>=592 passed, 0 failed
```

## 输出：验证报告

完成上述 8 大类（A-H）后，按以下结构输出 JSON 报告：

```json
{{
  "environment": {{
    "container_tool": "orbstack|docker|lima",
    "image": "ubuntu:22.04",
    "python": "3.12.x",
    "node": "20.x",
    "claude_code": "2.x.x",
    "kimi_code": "0.14+",
    "vibesop": "7.3.x",
    "llm_provider": "deepseek|omlx|ollama",
    "skills_indexed": 102
  }},
  "results": {{
    "A.container_setup": {{"passed": true}},
    "B.agents_installed": {{"claude_code": true, "kimi_code": true, "pi_agent": "skipped"}},
    "C.llm_provider": {{"configured": true, "indexer_resolved_provider": "deepseek/deepseek-v4-flash"}},
    "D.skill_index": {{"indexed_count": 102, "failed_count": 0}},
    "E.config_generation": {{"claude_code": true, "kimi_cli": true, "pi": true}},
    "F.cli_routing": {{
      "F1_single": "diagnose (72%)",
      "F2_orchestrate": "3 steps with skill_ids",
      "F3_squad": "architect+implementer+reviewer+red_team",
      "F4_slash": "/vibe-list OK",
      "F5_explicit": "OK"
    }},
    "G.hook_integration": {{
      "G1_files_exist": true,
      "G2_claude_md_protocol": true,
      "G3_json_envelope_parsed": true,
      "G4_hook_returns_skill": "critical: must contain skill_id, not No matching skill found"
    }},
    "H.tests": {{"basedpyright_errors": 0, "pytest_passed": 592}}
  }},
  "p0_issues": [],
  "p1_issues": [],
  "conclusion": "pass: VibeSOP itself + agent config gen OK; G4 hook-to-skill is known P0"
}}
```

## 已知问题（不算验证失败，但要在报告中标记）

| ID | 描述 | 当前状态 |
|---|---|---|
| P0-hook-routing | `AgentRuntime.handle_query()` ORCHESTRATE 分支不传 analysis 给 router，导致 hook 返回 "No matching skill found"（CLI 同 query 正常） | 待修 v7.3.3 |
| P1-squad-summary | Multi-intent Reasoning 显示正确 skill，Execution Summary 全 fallback-llm | 显示 bug |
| P2-kimi-acp | Kimi Code 0.14.3 用新 ACP 协议，VibeSOP 当前生成旧 AGENTS.md 协议 | 配置可用但未利用 ACP |
| P3-pi-agent | 无官方 npm 包，仅验证配置文件生成 | 上游分发问题 |

## 直接调用

如果不想手动跑，可调内置 validator（覆盖 A/B/E/G1/H，不含 LLM/Index/Hook→Skill 验证）：

```bash
vibe prompt-chain validate --json
```

但**完整 e2e 必须手动跑 C/D/G3/G4** — 这些是 Round 1-3 教训显示 validator 还未覆盖的关键路径。
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
