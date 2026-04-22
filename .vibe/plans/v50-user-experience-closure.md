# VibeSOP v5.0 用户体验闭环计划

> **Status**: Active
> **Date**: 2026-04-21
> **Theme**: 基础设施已就绪，补齐用户可感知的"最后一公里"
> **Prior Review**: version_05.md product review + gstack-office-hours brainstorm

---

## 1. 背景

当前代码库已完成以下基础设施：

| 能力 | 代码状态 | 用户感知度 |
|------|---------|-----------|
| 8层路由 + Fallback LLM | ✅ 成熟 | ⚠️ 能看到 fallback 面板，但看不到"为什么其他技能没选中" |
| 质量评分驱动路由 | ✅ 已实现 | ⚠️ `vibe skills report` 有数据，但路由时不展示负向原因 |
| 多意图编排 | ✅ 已实现 | ⚠️ `--explain` 展示执行流，但用户不能干预计划 |
| 会话习惯学习 | ✅ 已实现 | ⚠️ 保存了状态，但用户不知道系统在"学习" |
| 技能描述传递 | ✅ 刚实现 | ⚠️ alternatives 带描述，但缺少"为什么被拒绝"的解释 |

**核心问题**：代码完成了 80%，但用户只能感知到 30%。系统做了大量智能工作，但用户看到的仍是黑盒。

---

## 2. 本轮迭代目标

> 让每一个智能决策都被用户理解、可干预、可反馈。

五大方向：

1. **负向透明度** — 展示"为什么其他技能被排除"
2. **编排交互层** — 用户可调整 ExecutionPlan
3. **技能工厂 MVP** — 降低技能创建门槛
4. **生态健康游戏化** — 让用户主动参与质量闭环
5. **生命周期状态机** — 为 SkillOS 打下架构基础

---

## 3. 具体任务

### Task 1: 负向路由透明度（Rejected Candidates）

**问题**: `--explain` 展示了 matched layers 和 alternatives，但没展示"哪些技能被哪些层排除了，为什么"。

**用户场景**: "我问了'安全扫描'，系统给我 fallback-llm。我理解没有匹配，但我想知道：我的 keyword-matcher 有没有接近的候选？是不是阈值设太高了？"

**实现方案**:

```python
# src/vibesop/core/models.py
class LayerDetail(BaseModel):
    # ... existing fields ...
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)

class RejectedCandidate(BaseModel):
    skill_id: str
    layer: RoutingLayer
    confidence: float
    reason: str  # "below threshold (0.6)", "namespace mismatch", "scope disabled"
```

**在各层收集 rejected candidates**:
- `KeywordMatcher`: 收集 `0.3 <= score < 0.6` 的候选（接近但未达阈值）
- `ScenarioMatcher`: 收集 trigger 部分匹配的 scenario
- `ExplicitMatcher`: 如果用户写了 `@skill` 但 skill 不存在，记录原因

**CLI 展示** (`--explain` / `--validate`):

```
🔍 Routing Decision Report

Query: "安全扫描我的代码"

Layers tried: explicit → scenario → ai_triage → keyword → tfidf → embedding → fuzzy → fallback_llm

❌ Keyword Matching
   Matched: None
   Near misses (below threshold):
     • gstack/guard (0.52) — "security audit" keyword overlap
     • gstack/scan (0.48) — "scan" keyword overlap
   Threshold: 0.6

❌ TF-IDF Matching
   Matched: None
   Near misses:
     • superpowers/security (0.55) — semantic overlap

🤖 Fallback LLM
   Reason: No confident skill match across all layers
   Nearest installed: gstack/guard (0.52)
```

**验收标准**:
- [ ] `--explain` 展示每层的 near-miss 候选（confidence < threshold 但 > threshold * 0.5）
- [ ] 每个 rejected candidate 有明确原因（阈值/作用域/禁用/命名空间）
- [ ] `--validate` 模式也展示 rejected candidates（帮助用户调试路由配置）
- [ ] 测试覆盖：阈值过滤、作用域过滤、禁用过滤

**工作量**: 3-4 天

---

### Task 2: 编排交互层（Execution Plan 用户干预）

**问题**: `orchestrate()` 生成了 ExecutionPlan，但用户只能[确认]/[使用单技能]/[跳过]，**不能调整步骤**。

**用户场景**: "系统把'分析架构并优化性能'分解为 3 步，但我只想做分析和优化，跳过评审。"

**实现方案**:

**A. CLI 交互增强** (`src/vibesop/cli/main.py`):

```python
# 当前选择：
choices = [
    questionary.Choice("✅ Confirm execution plan", value="confirm"),
    questionary.Choice("🔀 Use single skill", value="single"),
    questionary.Choice("📝 Skip skills, use raw LLM", value="skip"),
]

# 新增选择：
choices = [
    questionary.Choice("✅ Confirm execution plan", value="confirm"),
    questionary.Choice("✏️  Edit steps", value="edit"),  # 新增
    questionary.Choice("🔀 Use single skill", value="single"),
    questionary.Choice("📝 Skip skills, use raw LLM", value="skip"),
]
```

**B. 步骤编辑交互**:

```
✏️  Edit Execution Plan

Current steps:
  [✓] Step 1: superpowers-architect — Analyze architecture
  [✓] Step 2: gstack/review — Review code quality
  [✗] Step 3: superpowers-optimize — Optimize performance

  [↑] Move up  [↓] Move down  [✗] Remove  [+] Add step  [Done]
```

**C. 策略强制指定** (新增 CLI 选项):

```bash
# 强制使用串行策略
vibe route "分析并优化" --strategy=sequential

# 强制使用并行策略
vibe route "review 代码和文档" --strategy=parallel

# 让系统自动选择（默认）
vibe route "分析并优化" --strategy=auto
```

**在 `RoutingConfig` 中增加**:
```python
class RoutingConfig(BaseModel):
    # ... existing ...
    default_strategy: str = Field(default="auto")  # auto | sequential | parallel | hybrid
```

**D. 数据依赖可视化**:

在 `--explain` 展示 ExecutionPlan 时，用箭头展示数据流：

```
Execution Flow:
  📐 architect
     ↓ output: analysis_report
  🔍 review
     ↓ output: review_notes
  ⚡ optimize
     ↓ output: final_recommendations
```

**验收标准**:
- [ ] 用户在确认弹窗中可选择"Edit steps"
- [ ] 可删除、重排序步骤
- [ ] `--strategy` CLI 选项有效
- [ ] `--explain` 展示数据依赖箭头
- [ ] 编辑后的 plan 可保存到 tracker

**工作量**: 5-7 天

---

### Task 3: 技能工厂 MVP（`vibe skills create`）

**问题**: 创建技能需要手动写 `SKILL.md`，门槛高。没有技能创造者，市场就是空货架。

**目标**: 让用户用自然语言描述需求，自动生成技能骨架。

**实现方案**:

```bash
$ vibe skills create

? Skill name: security-audit
? Describe what this skill should do: 
  "Scan Python code for security vulnerabilities like SQL injection, 
   XSS, and hardcoded secrets"

? Trigger keywords (comma-separated): security, audit, scan, vulnerability
? Suggested namespace: gstack

Generating skill template...
✓ Created .vibe/skills/security-audit/SKILL.md
✓ Created .vibe/skills/security-audit/triggers.yaml

Next steps:
  1. Edit SKILL.md to refine the workflow
  2. Run `vibe skills validate security-audit` to test
  3. Run `vibe skills enable security-audit` to activate
```

**底层实现** (`src/vibesop/cli/commands/skills_cmd.py`):

```python
def create(
    name: str | None = typer.Option(None, help="Skill name"),
    description: str | None = typer.Option(None, help="What the skill does"),
    from_template: str | None = typer.Option(None, help="Base on existing skill"),
    interactive: bool = typer.Option(True, help="Interactive wizard"),
) -> None:
    """Create a new skill from natural language description or template."""
```

**如果提供了 `--from <skill>`**，复制现有技能作为模板：

```bash
vibe skills create --from gstack/review --name my-review
# 复制 gstack/review 的 SKILL.md，让用户修改
```

**如果提供了 LLM 支持**，用 LLM 生成 SKILL.md：

```python
# 使用本地模板 + 可选 LLM 增强
prompt = f"""
Create a SKILL.md for a VibeSOP skill with:
- name: {name}
- description: {description}
- triggers: {keywords}

Format:
---
id: {namespace}/{name}
name: {name}
description: {description}
intent: {intent}
---

# Workflow
1. ...
2. ...
"""
```

**验收标准**:
- [ ] `vibe skills create` 交互式向导可用
- [ ] `vibe skills create --from <skill>` 可复制模板
- [ ] 生成的 SKILL.md 符合格式规范
- [ ] 创建后立即可用 `vibe skills validate` 测试

**工作量**: 4-5 天

---

### Task 4: 技能生态健康游戏化

**问题**: `vibe skills report` 展示了数据，但用户没有动力去反馈或改进技能。

**目标**: 把"技能质量"变成用户愿意关注的游戏化指标。

**实现方案**:

**A. 每周健康报告** (`vibe skills health --ecosystem`):

```bash
$ vibe skills health --ecosystem

📊 Your Skill Ecosystem Health (Week of 2026-04-21)

Top Performers 🏆
  gstack/review        A  +0.05 boost  ████████░░ 45 routes
  superpowers/debug    A  +0.05 boost  ██████░░░░ 23 routes

Needs Attention ⚠️
  old-deploy-script    C  no change    ███░░░░░░░  2 routes
  
At Risk 🗑️
  legacy-test-skill    F  -0.05 demote ██░░░░░░░░  1 route
  Action: Run `vibe skills feedback --skill legacy-test-skill`
          or `vibe skills disable legacy-test-skill`

Feedback Opportunities 💡
  3 skills need more feedback to reach reliable grading:
  • ci-cd (1/3 routes) — Run it 2 more times!
```

**B. 成就徽章系统** (轻量级，存储在 session 或 config 中):

```python
# 当用户首次给出 feedback 时
console.print("🎖️  First Feedback Badge: You've started improving the ecosystem!")

# 当用户的技能被使用 10 次
console.print("🏆  Skill Champion: Your skill has been used 10 times!")

# 当所有技能都达到 Grade B+
console.print("✨  Quality Master: All your skills are performing well!")
```

**C. 在 `vibe route` 输出中暗示习惯学习**:

```
✅ Matched: deploy-k8s
   Confidence: 93%
   Layer: semantic
   💡 Habit boost applied (3rd similar query)
```

**验收标准**:
- [ ] `vibe skills health --ecosystem` 输出游戏化报告
- [ ] 首次 feedback 给予徽章提示
- [ ] habit boost 在路由结果中可见
- [ ] report 输出按 grade 分组（Top / Needs Attention / At Risk）

**工作量**: 3-4 天

---

### Task 5: SkillLifecycleState 状态机（架构基础）

**问题**: 技能只有 `enabled: true/false`，没有生命周期概念。version_05.md 要求预埋 `DRAFT → ACTIVE → DEPRECATED → ARCHIVED`。

**目标**: 为 v5.1 的"自治淘汰"打下数据模型基础。

**实现方案**:

```python
# src/vibesop/core/skills/lifecycle.py
from enum import StrEnum

class SkillLifecycleState(StrEnum):
    DRAFT = "draft"           # 刚创建，未激活
    ACTIVE = "active"         # 正常使用
    DEPRECATED = "deprecated" # 标记过时，仍可用但警告
    ARCHIVED = "archived"     # 已归档，不可路由但保留数据

class SkillLifecycle:
    """Manages skill lifecycle transitions."""
    
    def transition(self, skill_id: str, to_state: SkillLifecycleState) -> None:
        # 验证状态转换合法性
        # DRAFT → ACTIVE ✓
        # ACTIVE → DEPRECATED ✓
        # DEPRECATED → ACTIVE ✓
        # ACTIVE → ARCHIVED ✓ (需确认)
        # DRAFT → ARCHIVED ✓
        pass
    
    def auto_transition(self, skill_id: str) -> None:
        """基于评估数据自动建议状态转换。"""
        evaluation = evaluator.evaluate(skill_id)
        if evaluation.grade == "F" and evaluation.total_routes >= 10:
            return SkillLifecycleState.DEPRECATED
```

**在 `SkillConfig` 中增加**:

```python
class SkillConfig(BaseModel):
    # ... existing fields ...
    lifecycle_state: str = Field(default="active")
    deprecation_reason: str | None = None
    archived_at: str | None = None
```

**CLI 命令**:

```bash
# 查看生命周期状态
vibe skills lifecycle <skill-id>

# 手动转换状态
vibe skills lifecycle <skill-id> --set deprecated --reason "Replaced by gstack/guard-v2"

# 自动建议转换
vibe skills lifecycle --auto-review
# Output:
#   ⚠️  superpowers/old-debug (Grade F, 12 routes) → Suggest: DEPRECATED
#   [Apply] [Keep active] [Archive]
```

**在路由中的影响**:
- `DEPRECATED` 技能：仍可匹配，但 CLI 展示黄色警告
- `ARCHIVED` 技能：不参与路由，但保留历史数据用于评估

**验收标准**:
- [ ] `SkillLifecycleState` 枚举定义完成
- [ ] `SkillConfig` 增加 `lifecycle_state` 字段
- [ ] `vibe skills lifecycle` 命令可用
- [ ] 路由引擎自动跳过 `ARCHIVED` 技能
- [ ] `DEPRECATED` 技能路由时展示警告

**工作量**: 4-5 天

---

## 4. 时间线与里程碑

```
Week 1 (Days 1-5)
  ├─ Day 1-2: Task 1 负向透明度 — RejectedCandidate 模型 + 各层收集
  ├─ Day 3-4: Task 1 CLI 展示 + 测试
  └─ Day 5:    Task 1 收尾 + Task 2 启动

Week 2 (Days 6-10)
  ├─ Day 6-7: Task 2 编排交互 — Edit steps 弹窗 + 重排序/删除
  ├─ Day 8:   Task 2 --strategy CLI 选项
  ├─ Day 9:   Task 2 数据依赖可视化
  └─ Day 10:  Task 2 测试 + 集成

Week 3 (Days 11-15)
  ├─ Day 11-12: Task 3 技能工厂 — vibe skills create 交互向导
  ├─ Day 13:    Task 3 --from 模板复制 + LLM 生成
  ├─ Day 14-15: Task 3 测试 + Task 4 启动

Week 4 (Days 16-20)
  ├─ Day 16-17: Task 4 生态健康 — --ecosystem 报告 + 徽章系统
  ├─ Day 18:    Task 4 habit boost 可见性
  ├─ Day 19-20: Task 5 SkillLifecycleState + CLI 命令
```

**里程碑**:
- **M1 (Day 5)**: 用户调试路由时能看到"为什么没匹配"
- **M2 (Day 10)**: 多意图编排从"展示"升级为"可干预"
- **M3 (Day 15)**: 用户可用自然语言创建技能
- **M4 (Day 20)**: 技能有生命周期状态，生态健康可感知

---

## 5. 与 version_05.md Roadmap 的对齐

| version_05 阶段 | 原计划 | 本计划调整 | 理由 |
|----------------|--------|-----------|------|
| v5.0 | 作用域 + 开关 | **透明度 + 编排交互 + 技能工厂** | 基础设施已就绪，补齐用户感知 |
| v5.1 | 评估 + 市场 | **生命周期状态机 + 生态健康游戏化** | 先治理现有技能，再建市场 |
| v5.2 | 推荐 + 发现 | **SkillMarket + 社区分享** | 依赖 v5.1 的稳定基础 |

---

## 6. 风险与缓解

| 风险 | 影响 | 缓解 |
|-----|------|------|
| Task 2 交互复杂度过高 | 中 | 先做"删除/重排序"，"添加步骤"列为 Phase 2 |
| Task 3 LLM 生成质量不稳定 | 低 | 默认使用本地模板，LLM 为可选增强 |
| Task 5 状态机引入 breaking change | 中 | `lifecycle_state` 默认 `"active"`，向后兼容 |
| 4 周工作量压缩 | 中 | Task 4 徽章系统可简化为纯文本提示，不做持久化存储 |

---

## 7. 立即决策项

1. **Task 2 的范围**: 是否包含"添加步骤"，还是只做"删除/重排序"？
2. **Task 3 的 LLM 依赖**: 是否必须等 LLM 集成就绪，还是先用模板方案？
3. **Task 4 徽章持久化**: 徽章存在 session 文件还是独立存储？
4. **Task 5 的自动转换**: v5.0 是否实现 `auto_review`，还是只留手动转换？

---

*Plan written by gstack-office-hours structured deliberation*
