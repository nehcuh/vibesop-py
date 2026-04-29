# VibeSOP 核心场景能力分析

## 问题：Agent 内部集成能力评估

### 核心使用场景

在 AI Agent（Claude Code、Kimi CLI、OpenCode）内部，VibeSOP 需要：

1. **命令识别** - Agent 能否识别并使用 VibeSOP 命令
2. **上下文感知** - 能否智能感知对话上下文
3. **技能选择** - 能否正确选择合适的技能
4. **复杂意图识别** - 能否识别复杂的多意图查询
5. **意图拆解** - 能否拆解复杂意图为子任务
6. **串行/并行处理** - 能否实现任务的串行和并行执行

---

## 当前架构能力矩阵

| 能力 | 实现状态 | CLI暴露 | Python API | Agent集成 | 说明 |
|------|---------|---------|------------|-----------|------|
| **基础路由** | ✅ 完整 | ✅ `vibe route` | ✅ UnifiedRouter | ✅ AgentRouter | 7层路由 pipeline |
| **上下文感知** | ✅ 完整 | ✅ `vibe session` | ✅ SessionContext | ✅ check_reroute() | 多轮对话追踪 |
| **AI Triage** | ✅ 完整 | ❌ 需配置 | ✅ TriageService | ✅ set_llm() | 需 LLM provider |
| **多意图检测** | ✅ 完整 | ❌ **未暴露** | ✅ MultiIntentDetector | ✅ detect_intents() | 启发式+LLM |
| **任务拆解** | ✅ 完整 | ❌ **未暴露** | ✅ TaskDecomposer | ✅ decompose() | LLM 拆解 |
| **执行计划** | ✅ 完整 | ❌ **未暴露** | ✅ PlanBuilder | ✅ build_plan() | 串行步骤 |
| **完整编排** | ✅ 完整 | ❌ **未暴露** | ✅ UnifiedRouter.orchestrate() | ✅ orchestrate() | 一站式 API |
| **并行执行** | ⚠️ 部分 | ❌ **未暴露** | ❌ **未实现** | ❌ **未暴露** | 仅串行支持 |

---

## 关键发现

### 1. CLI 暴露不完整 🔴

**问题**：编排能力（多意图检测、任务拆解、执行计划）已实现但未通过 CLI 暴露。

**影响**：
- 用户无法通过 `vibe` 命令使用这些功能
- Agent 无法通过 shell 调用获得编排结果

**证据**：
```bash
# 这些命令不存在：
vibe orchestrate "帮我测试并审查代码"
vibe decompose "先设计架构，再实现，最后测试"
vibe plan "重构模块并添加文档"
```

### 2. Agent 集成路径不完整 🟡

**当前状态**：
```python
# ✅ 可以做：基础路由 + AI triage
router = AgentRouter()
router.set_llm(agent_llm)
result = router.route("简单查询")

# ❌ 无法做：复杂意图处理
# 没有 API 用于：
# - 多意图检测
# - 任务拆解
# - 执行计划构建
```

### 3. 串行执行已实现，并行缺失 🟡

**ExecutionPlan 支持串行步骤**：
```python
ExecutionPlan(
    steps=[
        ExecutionStep(skill_id="architect", ...),  # 步骤1
        ExecutionStep(skill_id="tdd", ...),        # 步骤2
        ExecutionStep(skill_id="review", ...),     # 步骤3
    ]
)
```

**但缺少**：
- 并行步骤标记（哪些步骤可并行）
- 依赖关系定义（DAG）
- 并行执行调度器

---

## 架构问题分析

### 问题 1：两层 API 不一致

**UnifiedRouter** 有 `orchestrate()` 方法：
```python
# src/vibesop/core/routing/unified.py
def orchestrate(self, query, ...):
    # 返回 OrchestrationResult
```

**但 AgentRouter 没有暴露**：
```python
# src/vibesop/agent/__init__.py
class AgentRouter:
    # ❌ 没有 orchestrate() 方法
    # ❌ 没有 decompose() 方法
    # ❌ 没有 detect_multi_intent() 方法
```

### 问题 2：编排组件需要 LLM 但无注入路径

**TaskDecomposer 需要 LLM**：
```python
def __init__(self, llm_client: Any | None = None):
    self._llm = llm_client
```

**但 AgentRouter.set_llm() 只注入到 TriageService**：
```python
def set_llm(self, llm_provider):
    self._router.set_llm(llm_provider)
    # ❌ TaskDecomposer 没有得到 LLM
```

### 问题 3：执行计划 vs 技能执行的鸿沟

**VibeSOP 提供**：
- 执行计划（哪些步骤、什么顺序、用什么技能）

**但不提供**：
- 步骤执行器
- 状态持久化
- 错误恢复
- 结果传递

**这意味着**：Agent 收到 ExecutionPlan 后，需要自己：
1. 理解计划结构
2. 按顺序执行每个步骤
3. 管理步骤间状态
4. 处理失败情况

---

## 推荐解决方案

### ✅ 方案 A：完善 AgentRouter API（已实现）

```python
from vibesop.agent import AgentRouter, SimpleLLM, SimpleResponse

class AgentLLM(SimpleLLM):
    def call(self, prompt, max_tokens=100, temperature=0.1):
        return SimpleResponse(content=self._generate(prompt))

router = AgentRouter()
router.set_llm(AgentLLM())

# 1. 基础路由 ✅
result = router.route("帮我调试")

# 2. 多意图检测 ✅
detection = router.detect_intents("帮我测试并审查代码")

# 3. 任务拆解 ✅
sub_tasks = router.decompose("先测试，再审查")

# 4. 构建执行计划 ✅
plan = router.build_plan("测试并审查", sub_tasks)

# 5. 完整编排（一站式）✅
result = router.orchestrate("先测试再审查最后添加文档")
if result["is_multi_intent"]:
    for step in result["plan"]["steps"]:
        skill_content = router.load_skill(step["skill_id"])
        # Agent 按照技能步骤执行

# 6. 技能加载 ✅
skill_content = router.load_skill("gstack/review")
```

### ✅ 方案 B：添加编排 CLI 命令（已实现）

```bash
# 拆解任务
vibe decompose "先设计，再实现，最后测试"

# 完整编排
vibe orchestrate "测试并审查代码"
```

> 注：`vibe detect-intents` 和 `vibe plan` 未作为独立 CLI 命令暴露，其功能已内置于 `vibe orchestrate` 和 `vibe decompose` 中。

### ✅ 方案 C：执行计划 JSON 输出（已实现）

```bash
vibe orchestrate "测试并审查代码" --json
vibe decompose "测试并审查代码" --json
```

输出：
```json
{
  "plan_id": "abc123",
  "original_query": "测试并审查代码",
  "steps": [
    {"step": 1, "skill": "gstack/qa", "query": "...", "parallel": false},
    {"step": 2, "skill": "gstack/review", "query": "...", "parallel": false}
  ]
}
```

---

## 优先级建议

| 优先级 | 任务 | 工作量 | 影响 | 状态 |
|--------|------|--------|------|------|
| P0 | AgentRouter 暴露编排 API | 中 | 核心 | ✅ 已完成 |
| P0 | LLM 注入到所有编排组件 | 小 | 必须 | ✅ 已完成 |
| P1 | 添加编排 CLI 命令 | 中 | 用户体验 | ✅ 已实现 |
| P1 | 执行计划 JSON 输出 | 小 | 集成 | ✅ 已实现 |
| P2 | 并行执行支持 | 大 | 高级场景 | ⏳ 待实现 |
| P2 | 步骤执行器 | 大 | 完整方案 | ⏳ 待实现 |

---

## 结论

**当前状态（更新后）**：
- ✅ 路由引擎完整且强大
- ✅ 编排能力已实现
- ✅ **AgentRouter API 完整暴露**
- ✅ **LLM 注入到所有组件**
- ✅ **CLI 编排命令已暴露**（`vibe orchestrate`、`vibe decompose`）

**Agent 内部集成能力**：

| 需求 | 状态 | 说明 |
|------|------|------|
| 命令识别 | ✅ | Agent 可调用 Python API |
| 上下文感知 | ✅ | SessionContext 追踪多轮对话 |
| 技能选择 | ✅ | 7层路由 + AI Triage |
| 复杂意图识别 | ✅ | MultiIntentDetector |
| 意图拆解 | ✅ | TaskDecomposer with LLM |
| 串行处理 | ✅ | ExecutionPlan 串行步骤 |
| 并行处理 | ⏳ | 待实现 DAG 调度器 |

**剩余差距**：
1. ~~CLI 暴露编排命令~~ ✅ 已完成（`vibe orchestrate`、`vibe decompose`）
2. ~~执行计划 JSON 输出~~ ✅ 已完成（`--json` 支持）
3. 并行执行 DAG 调度器（高级场景，部分实现）
3. 并行执行支持（高级场景）
4. 步骤执行器（完整自动化）
