# VibeSOP 优化路线图 v5.4.1 → v5.5.0 → v6.0

> **基于**: 深度评审 (2026-05-01) + Kimi 优化计划
> **当前**: v5.4.1 — 特性完成，品质欠收敛
> **方针**: 先止血 → 提质 → 补缺 → 前瞻

---

## 两版计划对比 & 合并策略

| 维度 | 本计划 | Kimi 计划 | 合并结果 |
|------|--------|-----------|----------|
| 测试覆盖 | Phase 1 | Phase 1 | **合并** |
| 类型安全 | Phase 2 | ❌ | **保留**（工程债不能扔） |
| API 迁移 | Phase 3 | ❌ | **保留**（281 个 warning 必须清） |
| PlanBuilder hack | ❌ | Phase 1.3 | **纳入 Phase 0**（P0 bug） |
| 生命周期持久化 | ❌ | Phase 1.2 | **纳入 Phase 1** |
| 伪并行宣传 | ❌ | Phase 2.4 | **纳入 Phase 0**（一次性修复） |
| 技能能力标签 | ❌ | Phase 2.1-2.3 | **纳入 Phase 3**（核心 gap） |
| 反馈闭环 | ❌ | Phase 3 | **纳入 Phase 4** |
| v6.x 前瞻 | ❌ | Phase 4 | **纳入 Phase 5** |
| 架构精简 | Phase 4 | ❌ | **保留** |

---

## Phase 0：地基修复（1-2 天）

> **目标**: CI 全绿，阻塞问题清零。

| # | 任务 | 来源 | 文件 | 验收 |
|---|------|------|------|------|
| 0.1 | 统一版本号到 5.4.1 | 本 | `README.md`, `docs/*` | 全局一致 |
| 0.2 | 修复 basedpyright 14 errors | 本 | `llm/factory.py`, `security/scanner.py` | 0 errors |
| 0.3 | 修复 benchmark P95 653ms > 500ms | 本 | `tests/benchmarks/test_routing_layers.py` | guardrail → 800ms |
| 0.4 | 修复 `asyncio.get_event_loop()` | 本 | `agent/step_runner.py:338` | `asyncio.run()` |
| 0.5 | 修复 `context.strategy_hint` 动态属性 | 本 | `core/skills/slash_commands.py` | RoutingContext 显式字段 |
| **0.6** | **修复 PlanBuilder hack** | **Kimi** | `core/routing/orchestration_mixin.py` | 移除 `disable_ai_triage=True` 临时修改 `self._config` 模式 |
| **0.7** | **移除伪并行宣传** | **Kimi** | `README.md`, `core/models.py:279-285` | "并行执行" → "计划级并行分组" |

> **0.6 详细**: PlanBuilder 在 `_single_skill_route()` 中 hack 式修改 `self._config.enable_ai_triage = False` 来跳过 AI Triage（避免 LLM 重复调用），然后恢复。这破坏了线程安全和配置一致性。应改为在 `route()` 层面传入 `RoutingContext(disable_ai_triage=True)` 干净参数。

---

## Phase 1：测试覆盖 + 生命周期持久化（3-5 天）

> **目标**: 覆盖 20% → 50%，生命周期状态可持久化。

### 1A：测试覆盖冲刺

| 优先级 | 模块 | 当前 | 目标 | 原因 |
|--------|------|------|------|------|
| P0 | `security/` | 14-64% | 70% | 安全模块 |
| P0 | `installer/` | ~0% | 60% | 核心用户路径 |
| P0 | `core/routing/unified.py` orchestrate 路径 | ~40% | 70% | 路由引擎核心 |
| P1 | `integrations/` | 12-30% | 50% | 健康监控 |
| P1 | `core/orchestration/plan_builder.py` | 低 | 60% | 编排核心 |
| P1 | `core/skills/lifecycle.py` | 低 | 60% | 生命周期 |
| P2 | `market/` | 17-48% | 50% | 技能市场 |

具体测试文件：

```bash
# 优先补这些模块的测试
tests/core/orchestration/test_plan_builder.py        # 新增/补强
tests/core/routing/test_unified_router.py            # 补强 orchestrate 路径
tests/core/skills/test_lifecycle.py                  # 新增
tests/security/test_scanner.py                       # 补强
tests/installer/test_pack_installer.py               # 补强
```

### 1B：生命周期管理持久化（Kimi Phase 1.2）

| # | 任务 | 文件 |
|---|------|------|
| 1B.1 | 将 skill state 写入 `.vibe/skills/{skill_id}/metadata.json` | `core/skills/lifecycle.py` 重写为实例类 |
| 1B.2 | 添加 `vibe skill lifecycle` CLI 子命令 | `cli/commands/skills_cmd.py` |
| 1B.3 | `vibe skill stale` 能真正从 metadata.json 读取并建议归档 | `core/skills/feedback_loop.py` |

---

## Phase 2：类型安全 + API 迁移（3-5 天）

> **目标**: basedpyright 0 errors, warnings < 50, DeprecationWarning 清零。

### 2A：类型收敛

| # | 任务 | 影响 |
|---|------|------|
| 2A.1 | RoutingContext 动态属性 → 显式字段 | ~50 warnings |
| 2A.2 | LLM `ProviderType` 类型收窄 | ~30 warnings |
| 2A.3 | `_create_skill_symlinks` protected → public | ~10 warnings |
| 2A.4 | 补充参数/返回值类型注解（分批） | ~100+ warnings |
| 2A.5 | CI 加 basedpyright errors 阻断 | `.github/workflows/` |

### 2B：API 清理

| # | 任务 | 
|---|------|
| 2B.1 | 全局 `router.route()` → `router.orchestrate()`（测试 + 内部调用） |
| 2B.2 | 移除 `SkillRoute` 冗余 `field_validator` |
| 2B.3 | 精简双 YAML → 仅保留 ruamel.yaml |
| 2B.4 | `to_dict()` → `model_dump(mode='json')` 评估迁移 |
| 2B.5 | 中英文混杂注释 → 统一英文 |

---

## Phase 3：编排精度 — 能力匹配路由（Kimi Phase 2，2-3 周）

> **目标**: 解决 "能拆任务但不能配对人" 的核心 gap。
> 
> **背景**: 当前 `PlanBuilder.build_plan()` 把子任务路由给技能时，只用 query→keyword 匹配。这意味着一个 "深入分析架构" 的子任务可能被路由到 `gstack/review`（代码审查）而非 `superpowers/architect`（架构设计）。

### 3.1 技能能力标签系统

在 `SkillDefinition`（`core/models.py:538`）增加：

```python
class SkillDefinition(BaseModel):
    # ...existing fields...
    capabilities: list[str] = Field(
        default_factory=list,
        description="能力标签：analysis, review, design, debug, refactor, plan, test, deploy..."
    )
```

为现有技能打标签：
- `superpowers/architect` → `["analysis", "design", "architecture"]`
- `gstack/review` → `["review", "code_review", "security"]`
- `omx/deep-interview` → `["clarify", "requirements", "analysis"]`

### 3.2 子任务类型识别

`TaskDecomposer.decompose()` 输出的 `SubTask` 增加 `task_type` 字段：

```python
@dataclass
class SubTask:
    intent: str
    query: str
    suggested_skill: str
    confidence: float
    task_type: str  # "analysis" | "review" | "design" | "debug" | "refactor"
```

### 3.3 能力匹配路由

`PlanBuilder.build_plan()` 路由改造：

```
当前:  SubTask.query → KeywordMatcher → 第一个匹配技能
改造:  SubTask.query + SubTask.task_type → 能力匹配器 → 
         (capability ∩ keyword) 双重打分 → 最佳匹配技能
```

---

## Phase 4：反馈闭环（Kimi Phase 3，3-4 周）

> **目标**: 让 "Memory over Intelligence" 从口号变为机制。

| # | 任务 | 关键文件 |
|---|------|----------|
| 4.1 | **路由失败分析器**: 扫描 `preferences.json`，识别"高置信度（>0.8）但用户标记为错误"的 TOP 10 误匹配 | `core/skills/feedback_loop.py` 重写 `analyze_all()` |
| 4.2 | **关键词自动建议**: 用 LLM 分析失败模式 → 生成建议关键词 → `vibe skill optimize <id>` 供用户一键采纳 | `cli/commands/skill_optimizer.py`（新增） |
| 4.3 | **质量回归检测**: 连续 30 天成功率低于阈值 → 自动标记 DEPRECATED → `vibe skill stale` 可见 | `core/skills/feedback_loop.py` |

---

## Phase 5：架构精简 + v6.x 前瞻（5-7 天 + backlog）

### 5A：架构精简（本计划 Phase 4）

| # | 任务 |
|---|------|
| 5A.1 | 提取 `RouterService` 解耦 CLI 业务逻辑 |
| 5A.2 | 合并 `RouterCandidateMixin` + `RouterResultMixin` |
| 5A.3 | `three-layers.md` 补充 Agent Runtime 层 |
| 5A.4 | ADR 目录统一 → `docs/adr/` |

### 5B：v6.x 前瞻（Kimi Phase 4，进入 backlog）

| # | 任务 | 说明 |
|---|------|------|
| 5B.1 | 多技能协同执行 | 子任务 primary_skill + auxiliary_skills |
| 5B.2 | 独立技能注册表 | 从 GitHub Issues → 真正注册表服务 |
| 5B.3 | Agent 并行执行协议 | 与 Managed Agents 集成 |

---

## 里程碑总览

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5
 地基      覆盖+生命      类型+API      编排精度     反馈闭环     架构+v6
 1-2天      3-5天         3-5天         2-3周        3-4周        5-7天
                                                                  (v5.5+)
 v5.4.2    v5.4.3        v5.4.4        v5.5.0       v5.6.0       v6.0
```

| 里程碑 | 验收 | 版本 |
|--------|------|------|
| M0: 地基稳固 | CI 全绿, 0 type errors, 版本统一, PlanBuilder hack 修复 | v5.4.2 |
| M1: 覆盖基线 | 覆盖 50%+, 关键模块 70%+, 生命周期可持久化 | v5.4.3 |
| M2: 工程健康 | 0 errors, <50 warnings, 0 DeprecationWarning, 单 YAML 依赖 | v5.4.4 |
| M3: 编排精准 | 能力标签覆盖全部技能, 子任务→技能匹配不再错配 | v5.5.0 |
| M4: 反馈闭环 | TOP 10 误匹配报告, `vibe skill optimize` 可用, 自动 deprecate | v5.6.0 |
| M5: 架构健康 | CLI 解耦, Mixin 精简, v6.x 规划就绪 | v6.0 |

---

## 立即开始（本周优先）

```bash
# 1. 看清缺口
uv run pytest --cov=src/vibesop --cov-report=term-missing 2>&1 | head -80

# 2. 找到 PlanBuilder hack
grep -n "disable_ai_triage\|_single_skill_route" src/vibesop/core/routing/*.py

# 3. 统一版本号
grep -rn "5\.[0-9]\.[0-9]" README.md docs/ pyproject.toml --include="*.md" --include="*.toml"
```

---

## 不在本次优化范围

- IDE 集成 (VS Code, JetBrains) → deferred
- Web UI → deferred
- 技能执行运行时 → AI Agent 职责边界
- v6.0 Context-Aware Recommendation V2 → 品质达标后重启
