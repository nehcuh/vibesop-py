# VibeSOP SkillOS 产品化优化计划

> **Status**: Draft
> **Date**: 2026-04-21
> **Based on**: version_05.md roadmap + product review session
> **Theme**: 让已实现的基础设施被用户感知，补齐兜底体验

---

## 1. 背景与核心矛盾

### 1.1 已具备的基础设施（代码已就绪）

| 基础设施 | 代码位置 | 状态 |
|---------|---------|------|
| 7层路由 + 透明度 | `UnifiedRouter`, `LayerDetail`, `--explain` | ✅ 成熟 |
| 多技能编排 | `MultiIntentDetector`, `TaskDecomposer`, `PlanBuilder` | ✅ 已实现 |
| 技能治理 | `enabled`, `scope`, `SkillLifecycleState`, `RoutingEvaluator` | ✅ 已实现 |
| 会话持久化 | `SessionContext.save/load`, `session_aware`, stickiness | ✅ 刚实现 |
| 评估体系 | `SkillEvaluation.quality_score`, A-F grades | ✅ 已计算 |

### 1.2 核心矛盾

> **"代码完成了 80%，但用户只能感知到 20%。"**

- 用户调用 `vibe route "安全扫描"` → 得到 "No match" → **感到困惑/失望**
- 用户不知道系统检测到了多意图（orchestrate() 是黑盒）
- `RoutingEvaluator` 算出了 A-F 等级，但路由时 Grade F 和 Grade A 被同等对待
- Session Persistence 保存了状态，但没有产生"越用越懂你"的体验

### 1.3 优化原则

1. **兜底优先**：确保用户永远不会被系统拒绝
2. **数据要用**：已计算的评分必须影响实际路由行为
3. **透明展示**：已实现的功能必须被用户感知
4. **渐进增强**：每个优化都不破坏现有体验

---

## 2. 优化计划总览

```
Phase A (Week 1-2): 兜底体验 + 质量驱动路由
  ├─ P0: 退化到普通 Agent（FALLBACK_LLM）
  └─ P1: Evaluator 数据驱动路由（quality_boost）

Phase B (Week 2-3): 编排可视化
  └─ P2: orchestrate() CLI 多意图展示

Phase C (Week 3-4): 智能增强
  ├─ P3: 会话习惯学习（habit_boost）
  └─ P4: 技能发现提示（skill_discovery_hint）
```

---

## 3. Phase A: 兜底体验 + 质量驱动路由

### 3.1 P0: 退化到普通 Agent（FALLBACK_LLM）

**问题**: 当无技能匹配时，用户看到 "No suitable match found"，这是一个死胡同。

**目标**: 系统优雅退化到 raw LLM 模式，让用户始终能继续工作。

**实现方案**:

```python
# src/vibesop/core/models.py
class RoutingLayer(StrEnum):
    # ... existing layers ...
    FALLBACK_LLM = "fallback_llm"  # 新增

# src/vibesop/core/routing/unified.py
class UnifiedRouter:
    def route(self, query, ...):
        # ... existing layer execution ...
        
        # No match found — fallback to raw LLM
        if not match:
            return self._build_fallback_result(query, candidates, context)
    
    def _build_fallback_result(self, query, candidates, context):
        return RoutingResult(
            primary=SkillRoute(
                skill_id="fallback-llm",
                confidence=1.0,
                layer=RoutingLayer.FALLBACK_LLM,
                source="builtin",
                metadata={
                    "reason": "No skill matched query",
                    "suggestion": "Try installing a relevant skill or rephrase your query",
                    "candidate_count": len(candidates),
                },
            ),
            alternatives=[],  # 或者放入最接近的候选
            routing_path=[..., RoutingLayer.FALLBACK_LLM],
            layer_details=[..., LayerDetail(
                layer=RoutingLayer.FALLBACK_LLM,
                matched=True,
                reason="No confident skill match; falling back to raw LLM",
            )],
            query=query,
            duration_ms=duration_ms,
        )
```

**CLI 输出设计**:

```
🤖 Fallback Mode

No installed skill matched your query:
  "安全扫描我的代码"

VibeSOP is a routing engine, not an executor.
Your AI Agent can still process this request using raw LLM.

💡 Suggestions:
  • Try more specific keywords (e.g., "audit security vulnerabilities")
  • Browse available skills: vibe skills list
  • Install a security skill: vibe install gstack/guard

[Continue with raw LLM] [Browse skills] [Search marketplace]
```

**配置选项**:
```yaml
# .vibe/config.yaml
routing:
  fallback_mode: "transparent"   # transparent | silent | disabled
  fallback_show_candidates: 3    # 展示最接近的 N 个候选
```

**验收标准**:
- [ ] `vibe route "nonsense query"` 不再返回 "No match"，而是进入 Fallback 模式
- [ ] `--explain` 模式下展示 FALLBACK_LLM 层详情
- [ ] 配置 `fallback_mode: "disabled"` 时保持原有 "No match" 行为（向后兼容）
- [ ] 测试覆盖率 > 90%

**工作量**: 2-3 天

---

### 3.2 P1: Evaluator 数据驱动路由（quality_boost）

**问题**: `RoutingEvaluator` 计算了 `quality_score` 和 A-F 等级，但这些数据没有被路由引擎使用。

**目标**: 让技能质量评分实际影响候选排序，实现"自治淘汰"的雏形。

**实现方案**:

```python
# src/vibesop/core/routing/optimization_service.py
class OptimizationService:
    def _apply_quality_boost(
        self,
        matches: list[MatchResult],
    ) -> list[MatchResult]:
        """Boost/demote skills based on evaluator quality scores."""
        from vibesop.core.skills.evaluator import RoutingEvaluator
        
        evaluator = RoutingEvaluator()
        grade_adjustment = {"A": 0.05, "B": 0.02, "C": 0.0, "D": -0.02, "F": -0.05}
        
        boosted = []
        for m in matches:
            evaluation = evaluator.evaluate(m.skill_id)
            if evaluation and evaluation.total_routes >= 3:
                adjustment = grade_adjustment.get(evaluation.grade, 0.0)
                new_confidence = min(max(m.confidence + adjustment, 0.0), 1.0)
                
                boosted_match = MatchResult(
                    skill_id=m.skill_id,
                    confidence=new_confidence,
                    score_breakdown={
                        **m.score_breakdown,
                        "quality_adjustment": adjustment,
                        "quality_grade": evaluation.grade,
                    },
                    matcher_type=m.matcher_type,
                    matched_keywords=m.matched_keywords,
                    matched_patterns=m.matched_patterns,
                    semantic_score=m.semantic_score,
                    metadata={
                        **m.metadata,
                        "quality_boost": True,
                        "grade": evaluation.grade,
                    },
                )
                boosted.append(boosted_match)
            else:
                boosted.append(m)
        
        boosted.sort(key=lambda x: x.confidence, reverse=True)
        return boosted
```

**在 apply_optimizations 中集成**:
```python
def apply_optimizations(self, matches, query, context=None):
    # ... preference boost ...
    # ... instinct boost ...
    # ... session stickiness ...
    matches = self._apply_quality_boost(matches)  # 新增
    # ... conflict resolution ...
```

**保守性设计**:
- 只有 `total_routes >= 3` 的技能才参与 quality_boost（避免样本不足）
- 调整幅度控制在 ±0.05 以内（避免 override 明确的意图匹配）
- 未评估的技能不受影响

**CLI 展示**:
```
✅ Matched: gstack/review
   Confidence: 82% (base: 77%, quality_boost: +0.05, grade: A)
   Layer: keyword
```

**验收标准**:
- [ ] Grade A 技能在同等 base confidence 下排名高于 Grade C
- [ ] Grade F 技能（<3 次使用）不受降级影响
- [ ] 未评估技能不受影响
- [ ] `--explain` 展示 quality_adjustment 明细
- [ ] 测试覆盖各种 grade 组合

**工作量**: 2-3 天

---

## 4. Phase B: 编排可视化

### 4.1 P2: orchestrate() CLI 多意图展示

**问题**: `orchestrate()` 已能检测多意图并生成执行计划，但 CLI 用户无法感知这一过程。

**目标**: 当系统检测到多意图时，清晰展示检测到的子任务、匹配的技能、执行策略，让用户理解并确认。

**实现方案**:

**A. 增强 `OrchestrationResult` 展示**:

```python
# src/vibesop/cli/orchestration_report.py
def render_orchestration_explain(result: OrchestrationResult, console: Console):
    """Rich-render the multi-intent detection process."""
    
    # 1. 展示多意图检测结果
    console.print("\n[bold cyan]🔀 Multi-Intent Detection[/bold cyan]\n")
    
    detector = result.detection_metadata  # 需要新增字段
    console.print(f"Original query: [dim]'{result.original_query}'[/dim]")
    console.print(f"Detected intents: {len(detector.sub_tasks)}")
    
    for i, task in enumerate(detector.sub_tasks, 1):
        console.print(f"  {i}. {task.intent} → {task.suggested_skill} ({task.confidence:.0%})")
    
    # 2. 展示执行策略
    console.print(f"\n[bold]Execution Strategy:[/bold] {result.plan.strategy.value}")
    for step in result.plan.steps:
        deps = f" (depends on: {', '.join(step.dependencies)})" if step.dependencies else ""
        console.print(f"  Step {step.order}: {step.skill_id}{deps}")
    
    # 3. 单技能 fallback
    if result.single_fallback:
        console.print(f"\n[dim]Single-skill fallback:[/dim] {result.single_fallback.skill_id}")
```

**B. 在 `OrchestrationResult` 中增加透明度字段**:

```python
# src/vibesop/core/models.py
@dataclass
class OrchestrationResult:
    # ... existing fields ...
    detection_metadata: MultiIntentDetection | None = None  # 新增
    
@dataclass
class MultiIntentDetection:
    sub_tasks: list[SubTask]
    decomposition_method: str  # "llm" | "keyword" | "heuristic"
    confidence: float  # 对分解结果的整体置信度
```

**C. CLI 交互流程**:

```
$ vibe route "分析架构并优化性能"

🔀 Multi-Intent Detected (confidence: 94%)

Your request was decomposed into 2 sub-tasks:
  1. 📐 architectural_analysis → superpowers-architect (0.92)
  2. ⚡ optimization           → superpowers-optimize (0.89)

Execution Strategy: SEQUENTIAL
  Step 1: superpowers-architect (output feeds into Step 2)
  Step 2: superpowers-optimize  (uses architect's analysis)

💡 Single-skill fallback: superpowers-architect (0.87)
   Would you like to:
   [Execute plan] [Use single skill] [Edit steps] [Skip skills]
```

**验收标准**:
- [ ] 多意图检测时自动展示分解结果
- [ ] `--explain` 展示分解方法（LLM/keyword/heuristic）
- [ ] 用户可切换到单技能 fallback
- [ ] 测试覆盖多意图和单意图两种情况

**工作量**: 3-4 天

---

## 5. Phase C: 智能增强

### 5.1 P3: 会话习惯学习（habit_boost）

**问题**: Session Persistence 保存了 `current_skill`，但没有利用历史路由模式做个性化推荐。

**目标**: 当用户多次在相似查询后选择同一技能时，系统自动学习并优先推荐。

**实现方案**:

```python
# src/vibesop/core/sessions/context.py
class SessionContext:
    # ... existing ...
    
    def record_route_decision(self, query: str, selected_skill: str):
        """Record a routing decision for habit learning."""
        with self._lock:
            self._route_history.append(RouteDecision(
                query_pattern=self._extract_pattern(query),
                selected_skill=selected_skill,
                timestamp=time.time(),
            ))
            self._update_habit_patterns()
    
    def _update_habit_patterns(self):
        """Extract recurring query→skill patterns."""
        from collections import Counter
        
        patterns = Counter()
        for rd in self._route_history[-50:]:  # 最近 50 次
            patterns[(rd.query_pattern, rd.selected_skill)] += 1
        
        # 保留出现 3+ 次的模式
        self._habit_patterns = {
            pattern: skill for (pattern, skill), count in patterns.items()
            if count >= 3
        }
    
    def get_habit_boost(self, query: str) -> dict[str, float]:
        """Return skill→boost mapping for learned habits."""
        query_pattern = self._extract_pattern(query)
        if query_pattern in self._habit_patterns:
            return {self._habit_patterns[query_pattern]: 0.08}
        return {}
```

**在路由中使用**:
```python
# OptimizationService
matches = self._apply_habit_boost(matches, context)
```

**验收标准**:
- [ ] 同一查询模式出现 3 次后，对应技能获得 boost
- [ ] boost 仅在该查询模式匹配时生效（不是全局的）
- [ ] 保存到 session 文件，跨 CLI 调用持久化

**工作量**: 3-4 天

---

### 5.2 P4: 技能发现提示（skill_discovery_hint）

**问题**: 当用户查询需要未安装的技能时，系统只说 "No match"。

**目标**: 在 Fallback 模式下，提示用户可能需要的技能（基于关键词匹配已注册/市场的技能）。

**实现方案（MVP）**:

```python
# src/vibesop/core/routing/unified.py
def _build_fallback_result(self, query, candidates, context):
    # ... existing fallback logic ...
    
    # 查找类似已安装但未匹配的技能
    similar_installed = self._find_similar_skills(query, candidates)
    
    # 查找市场中未安装的技能（从 registry.yaml）
    similar_market = self._find_market_skills(query)
    
    metadata = {
        "similar_installed": similar_installed[:3],
        "similar_market": similar_market[:3],
    }
```

**CLI 输出**:
```
🤖 Fallback Mode

No skill matched "安全扫描我的代码"

💡 Did you mean?
   Installed skills (not confident match):
     • gstack/guard (65% keyword overlap)
   
   Available in marketplace:
     • superpowers/security (security audit skill)
     • gstack/scan (vulnerability scanner)

[Install gstack/guard] [Browse all security skills] [Continue with LLM]
```

**验收标准**:
- [ ] Fallback 模式展示最接近的已安装技能（即使 confidence < threshold）
- [ ] 展示市场中相关的未安装技能
- [ ] 提供一键安装入口

**工作量**: 3-5 天

---

## 6. 时间线与里程碑

```
Week 1
  Day 1-2: P0 FALLBACK_LLM 实现 + CLI 输出
  Day 3-5: P1 quality_boost 实现 + 测试

Week 2
  Day 1-2: P0/P1 测试完善 + lint + 文档
  Day 3-5: P2 orchestrate() 可视化 + detection_metadata

Week 3
  Day 1-2: P2 测试 + 交互流程打磨
  Day 3-5: P3 habit_boost 实现

Week 4
  Day 1-2: P3 测试 + 集成
  Day 3-5: P4 skill_discovery_hint MVP
```

**里程碑**:
- **M1 (Week 1 结束)**: 用户永远不会再看到 "No match" 死胡同
- **M2 (Week 2 结束)**: 高质量技能自动获得更多路由机会
- **M3 (Week 3 结束)**: 多意图编排过程对用户完全透明
- **M4 (Week 4 结束)**: 系统开始"学习"用户习惯并推荐技能

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解 |
|-----|------|------|
| quality_boost 过度影响路由 | 中 | 限制调整幅度 ±0.05，样本门槛 >=3 次 |
| FALLBACK_LLM 让用户困惑 | 低 | 配置项 `fallback_mode` 可关闭；输出文案清晰解释 |
| habit_boost 产生错误关联 | 低 | 仅基于精确 query pattern，不是模糊匹配；可配置关闭 |
| 多意图检测误报 | 中 | 设置整体 confidence 阈值（如 0.85）；低 confidence 时退化到单技能 |

---

## 8. 与 version_05.md 的 Roadmap 对齐

| version_05 阶段 | 本计划对应 | 状态 |
|----------------|-----------|------|
| v5.0: 作用域 + 开关 | 已完成（Phase 3 已交付） | ✅ |
| v5.1: 评估 + 分享 | P1 quality_boost, P4 discovery | 🔄 启动 |
| v5.2: 推荐 + 发现 | P3 habit_boost, P2 orchestration | 🔄 启动 |
| **新增**: 兜底体验 | P0 FALLBACK_LLM | 🔄 启动 |

---

## 9. 下一步决策

需要确认的问题：

1. **FALLBACK_LLM 的默认行为**: 默认 `transparent`（展示解释）还是 `silent`（静默退化）？
2. **quality_boost 的默认启用**: 默认开启还是保守地默认关闭？
3. **多意图检测阈值**: `orchestrate()` 只在整体 confidence > ? 时展示多意图分解
4. **是否先做 P0-P1 的 MVP PR 验证方向**，再进入 P2-P4？

---

*Plan written by gstack-office-hours + ralplan structured deliberation*
