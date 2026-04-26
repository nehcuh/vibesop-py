# VibeSOP 综合优化开发方案

> **Status**: Active
> **Date**: 2026-04-26
> **Based on**: 深度项目评审 + version_05.md ADR + 现有 4 份计划合并去重
> **Version**: v4.4.0 → v5.2.0
> **Branch**: `feature/comprehensive-optimization`

---

## 0. 方法论

### 分级体系

| 级别 | 定义 | 反应时间 |
|------|------|---------|
| **P0** | 产品谎报、数据伪造、用户直接撞墙 | 立即修复 |
| **P1** | 代码质量债、结构性缺陷、影响可扩展性 | 一周内 |
| **P2** | 功能缺失、体验短板、生态基建 | 按版本计划 |

### 去重策略

已存在 4 份独立计划，大量交叉。本方案执行**合并去重**原则：

| 已有计划 | 保留项 | 合并到本方案的 Phase |
|---------|--------|---------------------|
| `v5-quality-sprint.md` | P0 质量修复（斜线命令、冗余、空壳） | Phase 1 |
| `skillos-productization.md` | 兜底体验、质量驱动路由、编排可视化 | Phase 1 + Phase 2 |
| `v50-user-experience-closure.md` | 用户确认编排、生命周期状态机 | Phase 3 |
| `agent-runtime-platform-adaptation.md` | SkillInjector 实现 | Phase 1 |

---

## Phase 0: 文档完整性修复（P0，1 天）

> **目标**：消除所有数字不一致，让 README/ROADMAP/源码数据统一可信。

### Task 0.1: 修复版本号不一致

**问题**：`_version.py` = "4.3.0"，`pyproject.toml` = "4.4.0"
**操作**：统一 `_version.py` → "4.4.0"
**文件**：`src/vibesop/_version.py:1`

### Task 0.2: 修复覆盖率声明不一致

| 位置 | 当前值 | 修正为 |
|------|--------|--------|
| README.md badge | 94% | **删除 badge**（不可验证），改为文字 ">75%" |
| ROADMAP.md | 74% | 保留（真实值），增加"目标 >80%" |
| PROJECT_STATUS.md | 1555+ tests | 改为 "2044+ tests" |

### Task 0.3: 修复架构文档版本号

**文件**：`docs/architecture/ARCHITECTURE.md:3`
**操作**：Version 4.3.0 → 4.4.0，同时更新 7-layer / 10-layer 描述统一

### Task 0.4: 修复 ROADMAP 数据不实

| 字段 | 当前值 | 修正为 |
|------|--------|--------|
| Code Lines | ~49,000 | 更新真实值并标注目标 |
| Routing P95 | 225ms | 保留，增加优化计划引用 |
| Lint Errors | 114 | 更新为真实值（22） |

---

## Phase 1: 消除虚假完成态（P0，6 天）

> **目标**：所有标记 ✅ 的功能必须可验证。不存在"代码在但用户用不到"的功能。

### Task 1.1: 斜线命令从"约定"到"可工作"（2 天）

**现状**：斜线命令依赖 AI Agent 三层约定（AGENTS 指令 → bash → CLI），非平台原生命令但 README 将其标记为 ✅。

**方案**：

1. 在所有 AGENTS.md/CLAUDE.md 中将"斜线命令"统一改名为**"快捷命令 (CLI Quick Commands)"**
2. 强调使用方式为 `vibe route --slash "/vibe-help"`
3. 删除不存在的 TypeScript plugin 引用
4. Hook 脚本 `vibesop-route.sh` 增加 jq 不可用时的 fallback（grep 解析）

**涉及文件**：
- `src/vibesop/adapters/claude_code.py` — 更新 CLAUDE.md 模板措辞
- `src/vibesop/adapters/opencode.py` — 删除 TS plugin 引用，更新 AGENTS.md
- `src/vibesop/adapters/kimi_cli.py` — 将 vibe route 指令前置到文件顶部
- `src/vibesop/adapters/templates/shared/vibesop-route.sh.j2` — 增加 jq fallback
- `README.md:161-162` — 将 "Slash Commands" 改为 "快捷命令"
- `ROADMAP.md` — 将 "Slash Commands ✅" 改为 "CLI Quick Commands ⚠️（CLI 可用，平台依赖 AI 遵指令）"

**验收**：`vibe route --slash "/vibe-help"` 正常工作；三个平台模板措辞统一

---

### Task 1.2: 消除 Adapter 冗余代码（1 天）

**现状**：三个 Adapter 中 `_find_skill_content`、`_normalize_skill_type`、`_generate_fallback_skill_content` 完全重复。

**方案**：抽取到 `adapters/_shared.py`（已存在），三个 Adapter 改为 import 调用。

**涉及文件**：
- `adapters/claude_code.py` — 删除 ~23 行，改为 `from ._shared import`
- `adapters/opencode.py` — 删除 ~75 行
- `adapters/kimi_cli.py` — 删除 ~77 行

**验收**：三个 Adapter 不再有重复私有方法；所有 adapter 测试通过；总计删除 ~175 行

---

### Task 1.3: 统一 Hook 脚本生成（1 天）

**现状**：`opencode.py` 硬编码 113 行 bash，`kimi_cli.py` 硬编码 109 行 bash，行为不一致。

**方案**：统一到一个 Jinja2 模板 `templates/shared/hooks/vibesop-route.sh.j2`。

**涉及文件**：
- 新建 `adapters/templates/shared/hooks/vibesop-route.sh.j2`
- `opencode.py` — 删除硬编码，走模板
- `kimi_cli.py` — 删除硬编码，走模板
- 新建 `tests/adapters/test_hook_templates.py`

**验收**：三个平台 hook 由同一模板生成；无 jq 环境下可工作

---

### Task 1.4: 填上空壳实现（1 天）

**问题 A**：`agent/runtime/skill_injector.py:153-185` 所有平台分支都是 `pass`

**方案**：
```python
def inject_single_skill(self, skill_id: str, platform: str) -> str:
    content = self._load_skill_content(skill_id)
    if not content:
        return f"Skill {skill_id} not found. Install: vibe install {skill_id}"
    if platform == "claude-code":
        import json
        return json.dumps({"additionalContext": f"[SKILL: {skill_id}]\n{content[:2000]}"})
    return f"[VIBESOP SKILL: {skill_id}]\n{content[:2000]}"
```

**问题 B**：`core/sessions/tracker.py` 中 `GenericSessionTracker` 6 个抽象方法全 `pass`

**方案**：实现文件持久化逻辑。`record_tool_use()` 写入 `.vibe/sessions/tools.jsonl`

**问题 C**：`core/badges.py` 仅在 CLI 中 `print`，无持久化

**方案**：徽章状态存储到 `.vibe/badges.json`，`BadgeManager.award()` 防止重复颁发

**验收**：SkillInjector 三个平台返回有效内容；SessionTracker 可持久化记录；`vibe badges list` 可查看徽章

---

### Task 1.5: 路由确认逻辑统一（1 天）

**现状**：`_handle_single_result` 和 `_handle_orchestrated_result` 在 `cli/main.py` 中是两套独立的确认逻辑。

**方案**：抽取 `_run_unified_confirmation` 为通用函数。

**涉及文件**：`src/vibesop/cli/main.py`

**验收**：两类结果走同一确认入口；`--yes` 在两个路径都生效

---

## Phase 2: 兜底体验 + 质量数据驱动（P1，5 天）

> **目标**：用户永远不会被系统拒绝；已计算的质量评分真正影响路由决策。

### Task 2.1: 退化到普通 Agent（FALLBACK_LLM 产品化）（2 天）

**现状**：`unified.py` 中 `FALLBACK_LLM` 层已实现（路由无匹配时返回 `fallback_llm` 技能），但 CLI 展示不够友好。

**方案**：增强 CLI 展示，将当前 `render_fallback_panel` 升级为交互式体验：

```
🤖 没有匹配到已安装技能

查询: "安全扫描我的代码"

所有路由层均无自信匹配。AI Agent 可使用原始 LLM 处理此请求。

💡 建议:
  • 试试更具体的关键词 (如 "audit security vulnerabilities")
  • 浏览可用技能: vibe skills list
  • 安装安全类技能: vibe install gstack/guard

[继续使用原始 LLM] [浏览技能] [搜索市场]
```

**涉及文件**：
- `src/vibesop/cli/render/` — 升级 `render_fallback_panel`
- `src/vibesop/core/routing/unified.py` — 确保 FALLBACK_LLM 携带最近候选技能信息

**配置**：
```yaml
routing:
  fallback_mode: "transparent"  # transparent | silent | disabled
```

**验收**：无匹配时不再显示 "No match"，显示友好面板；`--explain` 展示 FALLBACK_LLM 层详情

---

### Task 2.2: Evaluator 数据驱动路由（quality_boost）（2 天）

**现状**：`RoutingEvaluator` 计算了 `quality_score` 和 A-F 等级（已存在于 `vibe skills report`），但路由引擎不消费这些数据。

**方案**：在 `OptimizationService` 中增加 `_apply_quality_boost`：

```python
# 保守性设计: 只有 total_routes >= 3 才参与调整
# 调整幅度: ±0.05（A:+0.05, B:+0.02, C:0, D:-0.02, F:-0.05）
# 确保 skill 排序中高评分技能优先于同等置信度的低评分技能
```

**涉及文件**：
- `src/vibesop/core/routing/optimization_service.py` — 新增 `_apply_quality_boost`
- `src/vibesop/core/routing/unified.py` — `_build_match_result` 中确保 quality 数据进入 metadata

**验收**：Grade A 技能在同等匹配分数下排名高于 Grade C；`--verbose` 展示 quality_adjustment 明细

---

### Task 2.3: SkillLifecycle 接入路由引擎（1 天）

**现状**：`SkillLifecycleState` 枚举和 `SkillConfig.lifecycle` 字段已定义，`SkillLifecycleManager.is_routable()` 已实现，但路由引擎未调用。

**方案**：在 `_candidate_manager.filter_routable()` 中检查 lifecycle：
- ARCHIVED → 排除
- DEPRECATED → 允许但附加 warning
- DRAFT → 排除（默认不可路由）

**涉及文件**：
- `src/vibesop/core/routing/candidate_manager.py` — `filter_routable()` 接入 lifecycle 检查

**验收**：ARCHIVED 技能不参与路由；DEPRECATED 技能路由时 CLI 展示警告；`vibe skill lifecycle <id> --set deprecated` 生效

---

## Phase 3: 用户体验闭环（P2，5 天）

> **目标**：让智能决策对用户可解释、可干预、可反馈。

### Task 3.1: 编排计划用户干预（2 天）

**现状**：`router.orchestrate()` 生成 ExecutionPlan 后直接返回。用户看到"这是一个编排任务"但无法编辑计划。

**方案**：实现 `plan_editor.py` 中已定义的交互式编辑 → 接入 CLI：

```
🔀 检测到 3 个意图 → 生成执行计划:

  1. [superpowers-architect] 架构分析
  2. [gstack/review]        代码评审  (依赖步骤 1)
  3. [superpowers-optimize]  优化方案  (依赖步骤 2)

  策略: sequential  |  预计步骤: 3
  置信度: 92% / 88% / 85%

[✅ 确认执行] [✏️ 编辑步骤] [🔄 单技能模式] [⏭ 跳过]
```

**涉及文件**：
- `src/vibesop/cli/main.py` — `_handle_orchestrated_result` 接入交互式确认
- `src/vibesop/cli/plan_editor.py` — 完善编辑功能（增删/移动/修改技能）

**配置**：
```yaml
routing:
  confirmation_mode: "always"  # always | never | ambiguous_only
```

**验收**：检测到多意图时展示执行计划并等待确认；用户可编辑步骤后重新生成；可用 `--yes` 或配置 `confirmation_mode: never` 跳过

---

### Task 3.2: 反馈闭环（反馈 → 评分 → 建议）（1 天）

**现状**：`AnalyticsStore` 记录执行数据，`FeedbackCollector` 收集满意度，但两者不联通。反馈收集后没有产生自动改进。

**方案**：建立最小闭环：

```
用户反馈满意度
       │
       ▼
AnalyticsStore.record_feedback()
       │
       ▼
RoutingEvaluator.reevaluate(skill_id)  ← 更新 quality_score
       │
       ▼
SkillConfig.usage_stats 更新           ← 数据预埋字段被消费
```

**涉及文件**：
- `src/vibesop/core/skills/evaluator.py` — 增加 `reevaluate()` 方法
- `src/vibesop/core/skills/config_manager.py` — 路由成功/失败时更新 `usage_stats`
- `src/vibesop/cli/main.py` — 路由命令后收集反馈的 `_collect_feedback` 接入闭环

**验收**：路由后满意度反馈被持久化；`vibe skills report` 评分基于真实使用数据；低满意度技能在后续路由中被降权

---

### Task 3.3: 会话感知 → 用户可感知（1 天）

**现状**：`SessionContext` 保存了状态，`PreferenceBooster` 使用了历史数据，但用户**不知道系统在"学习"**。

**方案**：在 `--verbose` 输出中展示 session stickiness 和 habit boost 来源：

```
📊 Session Context
   Current session: 3 routes, 2 unique skills
   Preferred skill: gstack/review (used 2× this session)
   Habit boost: +0.03 confidence from session stickiness
```

**涉及文件**：
- `src/vibesop/cli/routing_report.py` — 渲染 session stickiness 信息
- `src/vibesop/core/routing/unified.py` — 确保 metadata 传递 session 信息

**验收**：`--verbose` 输出展示 session 状态的 boost 来源

---

## Phase 4: 代码收敛（P1，4 天）

> **目标**：51K 行 → ~45K 行（减少 ~12%），核心模块行数控制在合理范围。

### Task 4.1: UnifiedRouter 进一步瘦身（1 天）

**现状**：1009 行。尽管已有 3 个 Mixin 提取，仍有优化空间。

**方案**：
- `_build_match_result` (~75 行) → 提取到 `execution_mixin.py`
- `_build_fallback_result` (~40 行) → 提取到 `execution_mixin.py`
- 多处 `_collect_alternatives_from_details` 逻辑统一为一个工具函数

**目标**：unified.py → ~850 行

---

### Task 4.2: CLI main.py 继续拆分（1 天）

**现状**：703 行，确认逻辑、渲染逻辑混在一起。

**方案**：
- `_handle_single_result` / `_handle_orchestrated_result` → 提取到 `cli/result_handler.py`
- `route()` 函数中的 live progress 包装 → 提取到 `cli/progress.py`

**目标**：main.py → ~500 行

---

### Task 4.3: 移除或冻结过度抽象（1 天）

**现状**：
- `core/sessions/tracker.py` — `ClaudeCodeSessionTracker`、`CursorSessionTracker` 两个子类全 `pass`，无实现价值
- `installer/quickstart_runner.py` — 148 行未覆盖（~12.9% 覆盖率），可能是死代码

**方案**：
- 暂时删除 tracker 子类的 `pass` 实现，统一用 `GenericSessionTracker`（Phase 1 已实现核心逻辑）
- 审计 `quickstart_runner.py`，确认是否仍被使用

---

### Task 4.4: 修复定位边界（明确"不执行技能"）（1 天）

**现状**：PHILOSOPHY.md 声明"不执行技能"，但代码中存在 `ExternalSkillExecutor`、`workflow_engine`、AST 安全执行器等。

**方案**：做出明确决策——

| 选项 | 推荐 |
|------|------|
| **A**: 彻底移除执行代码，只保留路由 | ❌ 风险大，测试依赖 |
| **B**: 保留执行能力但标记为 `internal/` | ⚠️ 测试需重构 |
| **C**: 保留现状，在 PHILOSOPHY.md 中澄清"有轻量级执行能力用于测试/验证" | ✅ **推荐** |

**操作**：
- PHILOSOPHY.md 增加一句："VibeSOP 保留轻量级本地执行能力用于开发者测试和验证，但在生产流程中，技能由 AI Agent 执行。"
- `ExternalSkillExecutor` 增加 docstring 明确"内部测试用途"

---

## Phase 5: 性能优化（P2，3 天）

> **目标**：路由 P95 从 225ms 降至 <150ms（阶段性目标，<100ms 留给 v5.2）

### Task 5.1: AI Triage 缓存策略增强（1 天）

**现状**：`CacheManager` 已实现 1 小时 TTL 缓存，但仅对完全相同的查询有效。

**方案**：增加 semantic similarity cache —— 相似查询复用缓存。

```python
# 使用 TF-IDF 向量计算查询相似度，相似度 > 0.85 视为同一缓存条目
# 比完整的 EmbeddingMatcher 快，比精确匹配覆盖面广
```

**涉及文件**：`src/vibesop/core/routing/cache.py`

---

### Task 5.2: Matcher warm-up 优化（1 天）

**现状**：`EmbeddingMatcher` 模型在 init 时已 warm-up（`_matchers_warmed`），但 `TF-IDF` 的 corpus 构建在首次 `route()` 时。

**方案**：在 `__init__` 中预构建 TF-IDF corpus（已有 `candidate_manager.get_cached_candidates()` 可用）。

---

### Task 5.3: 延迟加载非热路径依赖（1 天）

**现状**：`UnifiedRouter.__init__` 中初始了大量全部路径都需要的组件。

**方案**：
- `_preference_booster` → 仅在多候选冲突时实例化
- `_conflict_resolver` → lazy init
- `_cluster_index` → 仅在 matcher pipeline 需要时构建

---

## Phase 6: 生态基建（v5.1 预热，3 天）

> **目标**：为 v5.1 的 SkillMarket + Feedback Loop 做好数据模型和接口准备。

### Task 6.1: 消费预埋的 evaluation_context 字段（1 天）

**现状**：`SkillConfig` 有 `usage_stats`、`version_history`、`evaluation_context` 三个字段，但只有存储逻辑，无消费逻辑。

**方案**：定义 `evaluation_context` 的具体 Schema：

```python
class EvaluationContext(BaseModel):
    total_routes: int = 0
    successful_routes: int = 0
    satisfaction_scores: list[float] = Field(default_factory=list)
    last_evaluated_at: str | None = None
    keywords_triggered: list[str] = Field(default_factory=list)
    missed_queries: list[str] = Field(default_factory=list)  # 预留给 autoresearch
```

在 `RoutingEvaluator` 中消费这些数据计算 quality_score。

---

### Task 6.2: SkillMarket 接口标准化（1 天）

**现状**：`vibe market search` 仅调用 GitHub topic crawler，返回结构是临时 dict。

**方案**：定义 `SkillMarketEntry` 模型，为 v5.1 的真正市场做准备：

```python
class SkillMarketEntry(BaseModel):
    skill_id: str
    name: str
    description: str
    author: str
    version: str
    downloads: int = 0
    rating: float = 0.0
    reviews: int = 0
    compatibility: list[str] = Field(default_factory=list)  # ["claude-code", "opencode"]
    install_command: str
    source_url: str
```

**涉及文件**：
- `src/vibesop/core/models.py` — 新增 `SkillMarketEntry`
- `src/vibesop/market/crawler.py` — 返回 `SkillMarketEntry` 而非 dict

---

### Task 6.3: v5.1 autoresearch 接口预留（1 天）

**定义**：为 `FeedbackLoop → AutoSuggestion` 预留接口，不实现逻辑，只定义契约：

```python
class AutoSuggestionEngine(Protocol):
    """v5.1 autoresearch feedback loop interface."""
    def analyze_missed_queries(self, skill_id: str) -> list[str]:
        """Suggest keywords to add for missed queries."""
        ...
    def detect_quality_regression(self, skill_id: str) -> bool:
        """Whether skill quality has regressed."""
        ...
    def recommend_deprecation(self, skill_id: str) -> tuple[bool, str]:
        """Return (should_deprecate, reason)."""
        ...
```

**涉及文件**：新建 `src/vibesop/core/orchestration/auto_improver.py`（接口定义）

---

## 总结：版本 → Phase 映射

```
v4.4.1 (当前 + Phase 0-1，7 天)
  ├─ Phase 0:  文档完整性修复
  └─ Phase 1:  消除虚假完成态

v4.4.2 (Phase 2，5 天)
  ├─ 2.1: FALLBACK_LLM 产品化
  ├─ 2.2: quality_boost 数据驱动路由
  └─ 2.3: SkillLifecycle 接入路由引擎

v4.4.3 (Phase 3，5 天)
  ├─ 3.1: 编排计划用户干预
  ├─ 3.2: 反馈闭环
  └─ 3.3: 会话感知可视化

v4.5.0 (Phase 4-5，7 天)
  ├─ Phase 4:  代码收敛
  └─ Phase 5:  性能优化

v5.0.0 (Phase 6，3 天)
  └─ Phase 6:  生态基建（数据模型 + 接口预留）
```

**总计**：~27 个工作日，覆盖 6 个 Phase，18 个 Task

---

## 关键风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| Phase 4 代码删除破坏现有测试 | 高 | 每个 Task 独立 PR，CI 全量跑 |
| Phase 5 性能优化可能引入 bug | 中 | 仅改动缓存和 lazy-init，不改核心逻辑 |
| 多份方案交叉导致重复工作 | 中 | 本方案为唯一执行依据，其余归档 |
| v5.1 生态基建投入产出比不确定 | 低 | Phase 6 仅做接口预留，不写实现 |
