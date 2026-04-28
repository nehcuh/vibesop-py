# v5.2 透明度与执行闭环 — 填上最后缺口

> **Status**: ✅ Completed (all features verified as already implemented)
> **Date**: 2026-04-27
> **Closure note**: All planned tasks (SkillInjector, SessionTracker, Badge, rejected candidates, unified orchestrate, LLM multi-intent) were found to already exist in the codebase with full implementations and passing tests. No new code changes needed.

---

## 0. 背景

上一轮 v5.1 补齐了四大生态闭环（scope 隔离、retention 可见化、技能学习→创建→注册），本轮聚焦剩余的两类问题：

| 类别 | 问题 | 严重度 |
|------|------|--------|
| **空壳实现** | SkillInjector 注入逻辑为空、SessionTracker 6 方法全 pass、Badge 无持久化 | P0 |
| **路由体验** | 单技能路由黑盒（看不到候选、不能切换）、多意图检测仅正则（无 LLM 精度） | P1 |

v5-quality-sprint.md 已识别这些问题但未实施，本轮执行。

---

## 1. Phase A: 消灭空壳实现（P0）

### Task 1.1: SkillInjector 真正注入技能内容（2天）

**文件**: `src/vibesop/agent/runtime/skill_injector.py`

**现状**：三个平台分支 `inject_single_skill()` 全是 `pass`。

**实现**：

```python
class SkillInjector:
    def inject_single_skill(self, skill_id: str, platform: str) -> str:
        content = self._load_skill_content(skill_id)
        if not content:
            return f"Skill {skill_id} not found."

        if platform == "claude-code":
            return json.dumps({
                "additionalContext": f"\n\n[ACTIVE SKILL: {skill_id}]\n{content[:2000]}"
            })
        elif platform == "opencode":
            return (
                f"[VIBESOP ACTIVE SKILL: {skill_id}]\n"
                f"{content[:2000]}\n"
                f"[END SKILL: {skill_id}]"
            )
        elif platform == "kimi-cli":
            return (
                f"<!-- VIBESOP SKILL: {skill_id} -->\n"
                f"{content[:2000]}"
            )
        else:
            return content[:2000]  # Generic fallback

    def _load_skill_content(self, skill_id: str) -> str | None:
        """Load SKILL.md content for injection."""
        from vibesop.core.skills.parser import parse_skill_md
        from pathlib import Path

        search_dirs = [
            Path(".vibe/skills"),
            Path("core/skills"),
            Path.home() / ".config/skills",
        ]
        for base in search_dirs:
            skill_file = base / skill_id / "SKILL.md"
            if skill_file.exists():
                return skill_file.read_text()
        return None
```

**验收标准**：
- [ ] `inject_single_skill("systematic-debugging", "claude-code")` 返回有效 JSON
- [ ] `inject_single_skill("systematic-debugging", "opencode")` 返回含标记文本
- [ ] `inject_single_skill("systematic-debugging", "kimi-cli")` 返回 HTML 注释标记文本
- [ ] 不存在的技能返回 "not found" 提示
- [ ] 单元测试覆盖三个平台 + 缺失技能场景

---

### Task 1.2: SessionTracker 实现文件持久化（2天）

**文件**: `src/vibesop/core/sessions/tracker.py`

**现状**：`GenericSessionTracker` 6 个抽象方法全是 `pass`。

**实现**：

```python
class GenericSessionTracker:
    def __init__(self, storage_dir: Path | None = None):
        self._storage = storage_dir or Path(".vibe/sessions/tools.jsonl")
        self._storage.parent.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        return True

    def enable(self) -> bool:
        marker = Path(".vibe/sessions/active")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        return True

    def disable(self) -> bool:
        marker = Path(".vibe/sessions/active")
        if marker.exists():
            marker.unlink()
        return True

    def record_tool_use(self, tool_name: str, skill: str | None = None, **ctx) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "tool": tool_name,
            "skill": skill,
            "context": ctx,
        }
        with self._storage.open("a") as f:
            f.write(json.dumps(record) + "\n")

    def get_recent_tools(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self._storage.exists():
            return []
        records = []
        with self._storage.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records[-limit:]

    def check_reroute(self, current_query: str) -> str | None:
        """基于历史工具调用建议重路由的技能 ID 或 None。"""
        recent = self.get_recent_tools(limit=10)
        # 简单启发式：如果最近多次使用同一技能且与当前查询匹配
        skill_counts: dict[str, int] = {}
        for r in recent:
            if r.get("skill"):
                skill_counts[r["skill"]] = skill_counts.get(r["skill"], 0) + 1
        # 返回使用频率最高的技能
        if skill_counts:
            return max(skill_counts, key=skill_counts.get)
        return None
```

**验收标准**：
- [ ] `record_tool_use` 持久化到 `.vibe/sessions/tools.jsonl`
- [ ] `get_recent_tools` 返回最近 N 条记录
- [ ] `check_reroute` 基于历史给出合理建议
- [ ] `enable`/`disable` 通过 marker 文件控制

---

### Task 1.3: Badge 系统持久化（0.5天）

**文件**: `src/vibesop/core/badges.py`

**现状**：徽章仅在 CLI 中 `print`，不持久化。

**实现**：

```python
class BadgeManager:
    STORAGE_FILE = Path(".vibe/badges.json")

    def __init__(self):
        self._badges: dict[str, dict[str, Any]] = {}
        self._load()

    def award(self, badge_type: str, user_id: str = "default") -> bool:
        if user_id in self._badges and badge_type in self._badges[user_id]:
            return False  # Already awarded
        self._badges.setdefault(user_id, {})[badge_type] = {
            "awarded_at": datetime.now(UTC).isoformat(),
            "reason": self._badge_reasons().get(badge_type, ""),
        }
        self._save()
        return True

    def list_badges(self, user_id: str = "default") -> list[str]:
        return list(self._badges.get(user_id, {}).keys())

    def _badge_reasons(self) -> dict[str, str]:
        return {
            "first_feedback": "First feedback submitted",
            "skill_champion": "5+ skills enabled",
            "quality_master": "10+ feedback submissions",
            "ecosystem_guardian": "Cleaned up stale skills",
        }

    def _load(self) -> None:
        if self.STORAGE_FILE.exists():
            try:
                self._badges = json.loads(self.STORAGE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                self._badges = {}

    def _save(self) -> None:
        self.STORAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.STORAGE_FILE.write_text(json.dumps(self._badges, indent=2))
```

**验收标准**：
- [ ] 徽章持久化到 `.vibe/badges.json`
- [ ] 同一徽章不重复颁发
- [ ] 现有 `BadgeTracker` 无缝对接新 `BadgeManager`

---

## 2. Phase B: 路由透明度增强（P1）

### Task 2.1: 展示 rejected candidates + 单技能候选切换（3天）

**问题**：当前 `vibe route --explain` 只展示匹配过程，不展示"哪些技能被哪些层排除了，为什么"。单技能路由没有候选列表，用户无法切换。

**方案**：

#### 2.1a: LayerResult 增加 rejected_candidates

```python
# src/vibesop/core/models.py
class LayerDetail(BaseModel):
    layer: RoutingLayer
    matched: bool
    matched_skill: str | None = None
    matched_confidence: float | None = None
    reason: str = ""
    rejected_candidates: list[RejectedCandidate] = Field(default_factory=list)

class RejectedCandidate(BaseModel):
    skill_id: str
    confidence: float
    reason: str  # "below threshold (0.6 < 0.7)", "scope: other project", "disabled"
```

#### 2.1b: UnifiedRouter 各层收集 rejected

```python
# src/vibesop/core/routing/unified.py

def _run_keyword_layer(self, query, candidates, ...):
    matched = []
    rejected = []
    for c in candidates:
        score = self._keyword_match(query, c)
        if score >= self.config.min_confidence:
            matched.append((c, score))
        else:
            rejected.append(RejectedCandidate(
                skill_id=c.id,
                confidence=score,
                reason=f"below threshold ({score:.2f} < {self.config.min_confidence})",
            ))
    # ... return matched and rejected
```

#### 2.1c: CLI 展示及其它

在 `render_routing_report` 中增加 "Rejected Candidates" 部分：

```
=== Rejected Candidates ===
  ✗ gstack/qa — keyword match 0.58 (below threshold 0.60)
  ✗ custom/deploy — scope: belongs to other project
  ✗ old-benchmark — disabled by user
```

#### 2.1d: 单技能路由时允许切换

当 `--explain` 模式展示 rejected 列表后，允许用户从 rejected 中强制选择：

```
$ vibe route "安全扫描" --explain

=== Rejected Candidates (below threshold) ===
  2. gstack/guard — keyword: 0.52 | security: 0.58
  3. cso/review   — semantic: 0.45

💡 To use a rejected skill: press [2] for gstack/guard, [3] for cso/review
```

**验收标准**：
- [ ] `--explain` 展示每层 rejected candidates 及原因
- [ ] keyword 层 rejection 原因是 "below threshold (X < Y)"
- [ ] scope 层 rejection 原因是 "scope: other project"
- [ ] disabled 技能 rejection 原因是 "disabled by user"
- [ ] 用户可从 rejected candidates 中选择强制使用
- [ ] 不开启 `--explain` 时无性能影响（rejected 不计算）

---

### Task 2.2: 统一 orchestrate() 为单一路由入口（2天）

**问题**：当前 `route()` 和 `orchestrate()` 是两条独立路径。单意图走 `route()`，多意图走 `orchestrate()`。理论上所有请求都应先经过意图分解。

**方案**：

```python
# UnifiedRouter 内部
def _route_impl(self, query, context=None) -> OrchestrationResult:
    # 1. Detector: check for multi-intent
    detector = MultiIntentDetector()
    if detector.has_multi_intents(query):
        sub_tasks = detector.decompose(query)
        plan = self._build_execution_plan(sub_tasks)
        return OrchestrationResult(
            mode=OrchestrationMode.ORCHESTRATED,
            execution_plan=plan,
            # ...
        )

    # 2. Single intent: still go through orchestrate for unified output
    primary, alternatives, details = self._run_all_layers(query, self._get_candidates(), context)

    # Build a 1-step ExecutionPlan (single-skill is a degenerate orchestration)
    step = ExecutionStep(skill_id=primary.skill_id, confidence=primary.confidence, order=1)
    plan = ExecutionPlan(steps=[step], mode=ExecutionStrategy.SINGLE)

    return OrchestrationResult(
        mode=OrchestrationMode.SINGLE,
        execution_plan=plan,
        primary=primary,
        alternatives=alternatives,
        layer_details=details,
        # ...
    )
```

**CLI 层统一**：`main.py` 的 `route` 和 `orchestrate` 命令都调用同一个 `_handle_result`，由 `result.mode` 驱动渲染。

**验收标准**：
- [ ] `route()` 和 `orchestrate()` 在内部使用同一执行路径
- [ ] 单技能结果也包含 `execution_plan`（1-step plan）
- [ ] `--explain` / `--verbose` 对两类结果都生效
- [ ] 向后兼容：现有 `route()` 调用行为不变

---

## 3. Phase C: 多意图语义增强（P1）

### Task 3.1: MultiIntentDetector LLM+Regex 混合（2天）

**文件**: `src/vibesop/core/orchestration/multi_intent_detector.py`

**现状**：仅依赖中文连接词正则匹配（"然后/接着/以及/同时"）。

**方案**：

```python
class MultiIntentDetector:
    def __init__(self, llm_client=None):
        self._llm = llm_client
        # Fast path markers
        self._fast_markers = re.compile(
            r'(然后|接着|以及|同时|并且|还要|另外|此外|'
            r'then|also|and also|additionally|furthermore)'
        )
        # Over-decomposition guard words
        self._guard_words = {
            '测试', '运行', '查看', '显示', '列表', '帮助',
            'test', 'run', 'check', 'show', 'list', 'help',
        }

    def has_multi_intents(self, query: str) -> bool:
        # Guard: short queries or single-verb queries are single-intent
        if len(query.split()) < 4:
            return False

        # Fast path: regex
        if self._fast_markers.search(query):
            # Check for false positives (guard words)
            query_lower = query.lower()
            if any(w in query_lower for w in self._guard_words):
                return False
            return True

        # LLM path (if available)
        if self._llm:
            return self._llm_detect(query)

        return False

    def _llm_detect(self, query: str) -> bool:
        """Use LLM to detect if query contains multiple independent intents."""
        prompt = (
            "Determine if the following user request contains MULTIPLE "
            "independent tasks that could be handled by different coding skills. "
            "Reply ONLY 'yes' or 'no'.\n\n"
            f"Request: {query}"
        )
        response = self._llm.chat(prompt, max_tokens=5, temperature=0)
        return response.strip().lower() == "yes"

    def decompose(self, query: str) -> list[SubTask]:
        if self._llm:
            return self._llm_decompose(query)
        return self._regex_decompose(query)

    def _llm_decompose(self, query: str) -> list[SubTask]:
        """LLM-based task decomposition."""
        prompt = (
            "Break this request into independent sub-tasks. Each sub-task "
            "should map to a single coding skill (debug, review, test, analyze, "
            "refactor, architect, optimize, document, deploy, brainstorm). "
            "Return ONLY a JSON array with 'intent' and 'description' fields.\n\n"
            f"Request: {query}"
        )
        response = self._llm.chat(prompt, temperature=0)
        try:
            tasks = json.loads(response)
            return [
                SubTask(intent=t["intent"], description=t["description"], confidence=0.85)
                for t in tasks
            ]
        except (json.JSONDecodeError, KeyError):
            return self._regex_decompose(query)
```

**验收标准**：
- [ ] `decompose("分析架构并优化性能")` 返回 2+ 子任务
- [ ] `decompose("帮我调试这个错误")` 返回 1 个子任务（单意图）
- [ ] 无 LLM 时降级到正则分段
- [ ] guard words 正确过滤误报

---

## 4. 执行顺序与依赖

```
Week 1 (Phase A): 空壳 → 实体
  Day 1-2:  Task 1.1 SkillInjector 注入逻辑
  Day 3-4:  Task 1.2 SessionTracker 文件持久化
  Day 5:    Task 1.3 Badge 持久化

Week 2 (Phase B): 透明度
  Day 6-8:  Task 2.1 rejected candidates + 候选切换
  Day 9-10: Task 2.2 统一 orchestrate() 入口

Week 3 (Phase C): 语义增强
  Day 11-12: Task 3.1 MultiIntentDetector LLM+Regex 混合
  Day 13-14: 回归测试 + ROADMAP 同步更新
```

**依赖关系**：
- Task 2.2 依赖 Task 2.1（统一入口前需先有关键的 rejected 数据）
- Task 3.1 依赖 Task 1.1（LLM 分解需要 `set_llm(agent_llm)` 可用）
- Phase A 各任务独立，可并行

---

## 5. 验收总览

| Task | 验收项 | 当前状态 | 目标状态 |
|------|--------|---------|---------|
| 1.1 | SkillInjector 三个平台注入可用 | pass（空） | 返回有效内容 |
| 1.2 | SessionTracker 持久化工具调用 | pass（空） | JSONL 持久化 |
| 1.3 | Badge 不重复颁发 + 持久化 | print 即完 | 文件持久化 |
| 2.1 | rejected candidates 展示 | 无 | --explain 展示 |
| 2.1 | 单技能时切换候选 | 不可 | 可从 rejected 强制选 |
| 2.2 | route/orchestrate 统一入口 | 两条路径 | 同一 pipeline |
| 3.1 | LLM 语义意图分解 | 仅正则 | 正则+LLM 混合 |

---

## 6. 不在此计划内

以下已由其他计划覆盖或超出本轮范围：

- ❌ Scope 隔离强化（v51-skill-ecosystem-closure.md 已完成）
- ❌ Retention 可见化 + 归档（v51-skill-ecosystem-closure.md 已完成）
- ❌ 技能学习→创建→注册闭环（v51-skill-ecosystem-closure.md 已完成）
- ❌ Fallback LLM 兜底（skillos-productization.md 已实现）
- ❌ Quality boost 驱动路由（skillos-productization.md 已实现）
- ❌ 斜线命令修复（v5-quality-sprint.md Phase 1）
- ❌ Adapter 冗余消除（v5-quality-sprint.md Phase 1）
- ❌ ROADMAP 数据修正（v5-quality-sprint.md Task 3.3）

---

*Generated: 2026-04-27 | Status: ✅ Completed (all features verified as implemented)*
