# v5.1 技能生态闭环 — 补齐四大缺失链路

> **Status**: Draft
> **Date**: 2026-04-26
> **Based on**: 项目深度分析报告 + version_05.md ADR + PHILOSOPHY.md
> **Theme**: 让声明的"技能生态"闭环真正运转起来
> **Related**: skillos-productization.md（兜底+质量驱动）、v5-quality-sprint.md（修地基）

---

## 0. 背景诊断

上一轮深度分析发现，虽然 v4.4 Roadmap 声称以下能力均已 `✅`，但实际存在四个关键缺口：

| 漏洞 | Roadmap 声称 | 实际状态 | 用户影响 |
|------|-------------|---------|---------|
| **缺口1**: 对话学习→技能创建→自动注册 | instinct-learning ✅, skill-craft ✅ | 仅 SKILL.md 定义，无自动触发 | 用户需手动 `/skill-craft`，感知不到"学习" |
| **缺口2**: 安装技能→自理解→自注册触发 | skill-understanding ✅ | 真正实现完成 | 用户已可感知，但文档不清晰 |
| **缺口3**: 项目级技能隔离 | scope system ✅ | 枚举+字段存在，路由层无显式过滤 | `.vibe/skills/` 技能可能泄露到其他项目 |
| **缺口4**: 长期不用技能提醒/屏蔽 | retention system ✅, feedback loop ✅ | 评估逻辑完整，无 CLI 触发入口 | 用户不知道哪些技能该清理 |

> 核心矛盾：代码完成了 70-80%，但用户可感知的"技能操作系统体验"只有 20-30%。

---

## 1. 缺口 1：技能学习→创建→注册全自动闭环

### 1.1 现状

| 组件 | 文件 | 状态 |
|------|------|------|
| `InstinctLearner` | `src/vibesop/core/instinct/learner.py` | ✅ 已实现，学习路由偏好 |
| `instinct-learning` 技能 | `core/skills/instinct-learning/SKILL.md` | ⚠️ 仅为 AI Agent prompt 定义 |
| `skill-craft` 技能 | `core/skills/skill-craft/SKILL.md` | ⚠️ 仅为 AI Agent prompt 定义 |
| `RegistrySync` | `src/vibesop/core/skills/registry_sync.py` | ✅ 已实现，同步内置技能 |
| 自动触发机制 | — | ❌ 不存在 |

**关键问题**：`InstinctLearner` 能学习"用户说X→用技能Y"，但不能学习"用户反复做Z→应该创建一个新技能"。整个 `skill-craft` 流程依赖用户手动输入 `/skill-craft`，不自动。

### 1.2 方案设计

```
┌─────────────────────────────────────────────────────────────┐
│                   InstinctLearner 增强                        │
│                                                              │
│  当前: pattern → action (单跳路由学习)                        │
│  新增: pattern_sequence → suggested_skill (序列→技能建议)     │
│                                                              │
│  示例:                                                        │
│    序列: Bash:lint → Edit:fix → Bash:test → success(×5)      │
│    检测: 稳定 3+ 步序列，重复 ≥5 次，成功率 ≥ 80%             │
│    输出: InstinctCandidate(type="skill_suggestion", ...)     │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                SkillSuggestionCollector (new)                 │
│                                                              │
│  持久化到 .vibe/instincts/skill_candidates.jsonl              │
│  {                                                           │
│    "id": "cand_xxx",                                         │
│    "pattern_sequence": ["lint", "fix", "test"],              │
│    "success_rate": 0.85,                                     │
│    "occurrences": 7,                                         │
│    "suggested_name": "lint-fix-test-workflow",               │
│    "confidence": 0.78,                                       │
│    "status": "pending"                                       │
│  }                                                           │
│                                                              │
│  当候选 ≥ 3 个 且 session_count % N == 0 时 → 触发提醒       │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              CLI 提醒 + 一键生成 (CLI 增强)                    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ 💡 Skill Suggestion                                 │    │
│  │                                                     │    │
│  │ I noticed you've repeated this workflow 7 times:    │    │
│  │   lint → fix → test  (success rate: 85%)            │    │
│  │                                                     │    │
│  │ Would you like to save it as a reusable skill?      │    │
│  │ [y] Create skill [v] Preview [n] Dismiss [×] Never  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  用户确认 y → 自动:                                           │
│    1. 生成 SKILL.md (调用 skill-craft 模板)                   │
│    2. SkillAutoConfigurator 分析并生成路由配置                │
│    3. 安装到 .vibe/skills/ (项目级) 或 ~/.vibe/skills/ (全局) │
│    4. RegistrySync 注册                                      │
│    5. 下次路由自动匹配                                        │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 具体任务

#### Task 1.1: InstinctLearner 增加序列模式检测（2天）

**文件**: `src/vibesop/core/instinct/learner.py`

```python
@dataclass
class SequencePattern:
    """A detected repeatable sequence of actions."""
    steps: list[str]
    success_count: int
    total_count: int
    first_seen: datetime
    last_seen: datetime
    context_tags: list[str]

    @property
    def success_rate(self) -> float:
        return self.success_count / self.total_count if self.total_count else 0.0

    @property
    def is_candidate(self) -> bool:
        return (
            self.total_count >= 5
            and self.success_rate >= 0.8
            and len(self.steps) >= 3
        )


class InstinctLearner:
    # ... existing ...

    def record_sequence(self, steps: list[str], success: bool, context: str = "") -> SequencePattern | None:
        """Record a sequence of tool calls and detect repeatable patterns."""
        ...
```

**验收标准**:
- [ ] 连续 5 次相同 3 步序列，成功率 ≥ 80% → 生成 SkillCandidate
- [ ] 单元测试覆盖: 不同序列、边界条件、去重

---

#### Task 1.2: SkillSuggestionCollector 持久化候选（1天）

**新增文件**: `src/vibesop/core/skills/suggestion_collector.py`

```python
@dataclass
class SkillSuggestion:
    id: str
    pattern_sequence: list[str]
    suggested_name: str
    suggested_description: str
    confidence: float
    status: str  # "pending" | "dismissed" | "created"
    created_at: datetime

class SkillSuggestionCollector:
    def __init__(self, storage_dir: Path | None = None): ...
    def add_candidate(self, pattern: SequencePattern) -> SkillSuggestion: ...
    def get_pending(self) -> list[SkillSuggestion]: ...
    def should_prompt(self) -> bool:
        """当 pending ≥ 3 个时返回 True"""
    def dismiss(self, suggestion_id: str) -> None: ...
    def mark_created(self, suggestion_id: str, skill_id: str) -> None: ...
```

**验收标准**:
- [ ] 候选持久化到 `.vibe/instincts/skill_candidates.jsonl`
- [ ] `should_prompt()` 在 pending ≥ 3 时返回 True
- [ ] dismiss/mark_created 正常工作

---

#### Task 1.3: CLI 一键生成技能（2天）

**修改文件**: `src/vibesop/cli/commands/skill_craft.py`（或新增 `src/vibesop/cli/commands/skill_craft_cmd.py`）

```bash
# 查看候选技能
$ vibe skill suggestions

💡 Pending Skill Suggestions (3)

1. lint-fix-test-workflow (confidence: 0.85)
   Pattern: lint → fix → test
   Occurrences: 7 times, 85% success
   Tags: linting, testing, workflow

2. api-retry-handler (confidence: 0.78)
   Pattern: check-status → grep-logs → retry
   Occurrences: 5 times, 80% success
   Tags: api, error-handling

[y] Create all  [c] Choose  [n] Dismiss all  [q] Quit
```

```bash
# 一键创建
$ vibe skill create --from-suggestion lint-fix-test-workflow

Generating skill...
  ✓ SKILL.md created: .vibe/skills/lint-fix-test-workflow/SKILL.md
  ✓ Auto-analyzed: category=testing, priority=65
  ✓ Routing patterns: 3 generated
  ✓ Registered for routing

Use: vibe route "lint and fix" → lint-fix-test-workflow (92%)
```

**关键代码**（自动注册）:
```python
def create_skill_from_suggestion(suggestion_id: str, scope: str = "project") -> str:
    suggestion = collector.get(suggestion_id)
    # 1. 生成 SKILL.md
    skill_dir = scope_path / suggestion.suggested_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    generate_skill_md(suggestion, skill_dir / "SKILL.md")

    # 2. SkillAutoConfigurator 分析
    configurator = SkillAutoConfigurator()
    config = configurator.understand_and_configure(metadata, content, scope)

    # 3. 保存配置 → 路由自动包含
    configurator.save_config(config, scope_path)

    # 4. 标记候选为 created
    collector.mark_created(suggestion_id, skill_id)
    return skill_id
```

**验收标准**:
- [ ] `vibe skill suggestions` 展示所有 pending 候选
- [ ] `vibe skill create --from-suggestion <id>` 生成 SKILL.md + 配置 + 注册
- [ ] 生成后 `vibe route "lint and fix"` 能匹配到新技能

---

#### Task 1.4: Session End 钩子触发检查（1天）

**修改**: `session-end` SKILL.md 增加步骤，或在 `FeedbackLoop` 中增加 `should_suggest()`

```python
# src/vibesop/core/skills/feedback_loop.py
class FeedbackLoop:
    def end_of_session_check(self) -> dict[str, Any]:
        """Called at session end to check for suggestions."""
        suggestions = self.analyze_all()
        skill_candidates = self._collector.get_pending()

        return {
            "retention_actions": [s.action for s in suggestions if s.action != "none"],
            "skill_suggestions_pending": len(skill_candidates),
            "should_prompt": self._collector.should_prompt(),
        }
```

**验收标准**:
- [ ] Session end 时如有 3+ pending 候选 → CLI 提示
- [ ] 可配置: `vibe config set suggestions.auto_prompt false` 关闭

---

## 2. 缺口 3：项目级技能 Scope 隔离强化

### 2.1 现状

- `SkillScope.PROJECT` / `SkillScope.GLOBAL` 枚举已定义（`lifecycle.py:15`）
- `SkillConfigManager` 已支持 `scope` 字段
- `SkillLoader` 已从项目 `.vibe/skills/` 搜索（优先级最高）
- **但**：路由层 `UnifiedRouter` 未显式过滤 scope

### 2.2 方案设计

```
用户在工作目录 A:
  .vibe/skills/project-deploy → scope=project (只在项目 A 可见)

用户 cd 到工作目录 B:
  .vibe/skills/ 中无 project-deploy → 不加载，路由不可见

关键：scope 过滤应在 SkillLoader 层面完成（发现阶段），
     而非在每个 route() 调用时判断（性能考虑）
```

### 2.3 具体任务

#### Task 2.1: SkillLoader 增加 scope-aware 发现（1.5天）

**修改**: `src/vibesop/core/skills/loader.py`

```python
class SkillLoader:
    def __init__(self, project_root: str | Path = ".", ...):
        self.project_root = Path(project_root).resolve()
        self._project_hash = self._compute_project_hash()

    def _compute_project_hash(self) -> str:
        """Stable project identity for scope sharing across runs."""
        import hashlib
        return hashlib.md5(str(self.project_root).encode()).hexdigest()[:12]

    def discover_all(self, force_reload: bool = False) -> dict[str, LoadedSkill]:
        # ... existing discovery ...

        # Filter by scope
        filtered = {}
        for skill_id, definition in self._skill_cache.items():
            config = SkillConfigManager.get_skill_config(skill_id)
            if config and config.scope == "project":
                # Project skills only visible when project_root matches
                skill_project = config.metadata.get("project_hash")
                if skill_project and skill_project != self._project_hash:
                    continue  # Hide: this skill belongs to another project
            filtered[skill_id] = definition
        self._skill_cache = filtered
```

**验收标准**:
- [ ] 在项目 A 中 `vibe skills list` 不显示项目 B 的 project-scope 技能
- [ ] 全局技能在所有项目中可见
- [ ] 测试覆盖: 跨项目隔离 + 同项目可见

---

#### Task 2.2: SkillAutoConfigurator 写入项目标识（0.5天）

**修改**: `src/vibesop/core/skills/understander.py`

```python
def save_config(self, config: AutoGeneratedConfig, output_dir: Path) -> Path:
    config_data["skills"][config.skill_id]["metadata"]["project_hash"] = (
        hashlib.md5(str(Path.cwd().resolve()).encode()).hexdigest()[:12]
    )
    ...
```

**验收标准**:
- [ ] `vibe skill add` 安装 project-scope 技能时，自动绑定当前项目 hash

---

#### Task 2.3: CLI scope 命令（0.5天）

**修改**: `src/vibesop/cli/commands/skill_cmd.py`

```bash
# 查看技能 scope
$ vibe skill scope systematic-debugging
Scope: global
Available in all projects

# 设置项目级 scope
$ vibe skill scope my-custom-skill --project
Scope changed: global → project (bound to project: vibesop-py)

# 设为全局
$ vibe skill scope my-custom-skill --global
Scope changed: project → global
```

**验收标准**:
- [ ] `vibe skill scope <id>` 展示当前 scope
- [ ] `vibe skill scope <id> --project` 绑定到当前项目
- [ ] `vibe skill scope <id> --global` 提升为全局可用

---

## 3. 缺口 4：长期不用技能提醒 + 动态屏蔽

### 3.1 现状

| 组件 | 文件 | 状态 |
|------|------|------|
| `RoutingEvaluator` | `evaluator.py` | ✅ 5 维度 A-F 评分 |
| `RetentionPolicy` | `retention.py` | ✅ "remove"/"warn"/"highlight" 建议 |
| `FeedbackLoop` | `feedback_loop.py` | ✅ 支持 `auto_deprecate=True` |
| **CLI 触发** | — | ❌ 无入口让用户查看或有检查触发 |
| **定时/自动触发** | — | ❌ 无调度机制 |
| **动态屏蔽** | — | ❌ 弃用技能仍可被路由 |

### 3.2 方案设计

```
┌────────────────────────────────────────────────────────────────┐
│                     Retention 全链路                              │
│                                                                 │
│  触发时机                                                        │
│  ├─ vibe route 入口（每次路由时，异步标记检查，不阻塞）             │
│  ├─ vibe skills list 入口（每次列表末尾展示待清理技能）              │
│  ├─ vibe skills health（新增子命令，主动检查）                     │
│  └─ session-end 钩子（被动提醒）                                   │
│                                                                 │
│  提醒级别                                                        │
│  ├─ 30天+未用 + F级 → ⚠️  建议移除                                │
│  ├─ 60天+未用 + D级 → ⚡  警告                                    │
│  ├─ 90天+未用 + 任意 → 🔴 自动归档（不再参与路由）                  │
│  └─ A级 + 活跃使用 → ⭐  高亮推荐                                  │
│                                                                 │
│  屏蔽机制                                                        │
│  ├─ ARCHIVED 状态技能 → is_routable() 返回 False                  │
│  ├─ 用户可手动恢复: vibe skill enable <id>（从 ARCHIVED→ACTIVE）   │
│  └─ 自动归档 SQL: 90天未用 + 非 A/B 级 → auto-archive              │
└────────────────────────────────────────────────────────────────┘
```

### 3.3 具体任务

#### Task 3.1: `vibe skills health` — 展示所有待清理技能（1.5天）

**修改/新增**: `src/vibesop/cli/commands/skills_cmd.py`

```bash
$ vibe skills health

📊 Skill Health Report

🔴 Needs Attention (2)
  • gstack/old-benchmark — 97 days unused, quality: F (0.22)
    → Action: [archive] [ignore] [review]
  • superpowers/unused-test — 64 days unused, quality: D (0.45)
    → Action: [warn later] [archive] [ignore]

🟡 Watch List (3)
  • custom/migration — 35 days unused, quality: C (0.62)

⭐ Top Performers (2)
  • systematic-debugging — Active today, quality: A (0.94)
  • gstack/review — Active 2 days ago, quality: A (0.91)

[Apply all suggestions] [Review individually] [Quit]
```

```python
def health_command():
    loop = FeedbackLoop()
    suggestions = loop.analyze_all()

    console.print("\n[bold]📊 Skill Health Report[/bold]\n")

    # Group by severity
    critical = [s for s in suggestions if s.action == "deprecate"]
    warn = [s for s in suggestions if s.action == "warn"]
    boost = [s for s in suggestions if s.action == "boost"]

    if critical:
        console.print("[red]🔴 Needs Attention[/red]")
        for s in critical:
            console.print(f"  • {s.skill_id} — {s.days_since_last_use}d unused, quality: {s.grade}")

    if boost:
        console.print("[green]⭐ Top Performers[/green]")
        for s in boost:
            console.print(f"  • {s.skill_id} — quality: {s.grade}")
```

**验收标准**:
- [ ] `vibe skills health` 分三类展示：需关注 / 观察 / 优秀
- [ ] 支持 `--apply` 自动归档所有建议
- [ ] 支持 `--json` 输出机器可读报告

---

#### Task 3.2: 归档技能不可路由（修改 lifecycle）（0.5天）

**修改**: `src/vibesop/core/skills/lifecycle.py`

```python
@classmethod
def is_routable(cls, state: SkillLifecycle) -> bool:
    # 当前: DRAFT 和 ARCHIVED 不可路由, ACTIVE 和 DEPRECATED 可路由
    # 改变: DEPRECATED 超过 90 天自动变 ARCHIVED → 不再可路由
    return state == SkillLifecycle.ACTIVE
```

**同步修改** `SkillLoader.discover_all()` 过滤逻辑：
```python
# 当前: 过滤 ARCHIVED 和 disabled
# 新增: 也过滤 scope 不匹配的
if config.lifecycle == SkillLifecycleState.ARCHIVED.value:
    continue
# 新增: check auto-archive
if config.lifecycle == SkillLifecycleState.DEPRECATED.value:
    days_since = _compute_days_since(config.last_used)
    if days_since and days_since > 90:
        SkillConfigManager.set_lifecycle(skill_id, "archived")
        continue
```

**验收标准**:
- [ ] ARCHIVED 技能不出现在路由候选
- [ ] DEPRECATED + 未用 90 天 → 自动归档（按需触发，非扫描时）
- [ ] 测试: `is_routable(ARCHIVED) == False`

---

#### Task 3.3: 路由时可配置的"待清理"提示（1天）

**修改**: `src/vibesop/cli/main.py` — route 命令增加 post-route 检查

```python
# 在 route 命令结果输出后，异步检查 retention
def _check_stale_skills_post_route():
    """每 N 次路由后检查一次（避免性能影响）。"""
    stats = load_routing_counter()
    if stats["routes_since_last_check"] < 20:
        return  # 每 20 次路由检查一次

    loop = FeedbackLoop()
    suggestions = loop.analyze_all()
    critical = [s for s in suggestions if s.action == "deprecate"]

    if critical:
        console.print()
        console.print("[yellow]💡 Tip:[/yellow] You have [bold]{0}[/bold] unused skills.")
        console.print("   Run [bold]vibe skills health[/bold] to review.")
        console.print()

    reset_routing_counter()
```

**配置**:
```yaml
retention:
  check_interval: 20          # 每 N 次路由检查一次
  auto_prompt: true           # 是否在 CLI 自动提示
  auto_archive_days: 90       # 自动归档阈值
  reminder_at_startup: false  # 是否在启动时提醒
```

**验收标准**:
- [ ] 每 20 次 `vibe route` 后自动检查并提示
- [ ] 配置 `auto_prompt: false` 时静默
- [ ] 不影响路由性能（异步检查，<5ms overhead）

---

#### Task 3.4: RetentionPolicy 补全归档阈值逻辑（0.5天）

**修改**: `src/vibesop/core/skills/retention.py`

```python
class RetentionPolicy:
    def analyze_skill(self, skill_id: str) -> RetentionSuggestion:
        # ... existing rules ...

        # 新增: 90天+未用 + 非 A/B 级 → auto-archive
        if days_since is not None and days_since >= 90 and grade not in ("A", "B"):
            return RetentionSuggestion(
                skill_id=skill_id,
                action="archive",
                reason=f"Unused for {days_since} days, grade {grade} — auto-archive",
                ...
            )
```

**验收标准**:
- [ ] 90天未用 + Grade C/D/F → action="archive"
- [ ] 90天未用 + Grade A/B → 不触发（高质量技能保留）

---

## 4. 交叉依赖与执行顺序

```
Phase A (Week 1-2): Scope 隔离强化
  ├─ Task 2.1: SkillLoader scope-aware discovery
  ├─ Task 2.2: SkillAutoConfigurator 项目标识
  └─ Task 2.3: CLI scope 命令

Phase B (Week 2-3): Retention 可见化
  ├─ Task 3.1: vibe skills health 命令
  ├─ Task 3.2: 归档技能不可路由
  ├─ Task 3.3: 路由时提示检查
  └─ Task 3.4: RetentionPolicy 归档逻辑

Phase C (Week 3-4): 技能学习闭环
  ├─ Task 1.1: InstinctLearner 序列模式检测
  ├─ Task 1.2: SkillSuggestionCollector
  ├─ Task 1.3: CLI 一键生成技能
  └─ Task 1.4: Session End 钩子

Phase D (Week 5): 集成验证 + 文档更新
  ├─ E2E 测试: install → scope isolate → auto-learn → retention
  ├─ ROADMAP.md 更新（标记缺口为关闭）
  └─ README 新增 "技能生态" 章节
```

**依赖关系**：
- Phase B 不依赖 Phase A（可并行）
- Phase C 的 Task 1.3 依赖 Phase A 的 scope 系统（生成技能时需指定 scope）
- Phase A/B/C 均依赖现有的 `SkillAutoConfigurator`、`RoutingEvaluator`、`FeedbackLoop`（已就绪）

---

## 5. 验收总览

| 缺口 | 验收指标 | 当前 | 目标 |
|------|---------|------|------|
| 缺口1 | 从"发现模式"到"技能可用"全自动 | 0%（需手动） | 90%（用户一键确认） |
| 缺口2 | 已达成，本次仅增强文档 | 95% | 100% |
| 缺口3 | project-scope 技能跨项目不可见 | 部分 | 100% |
| 缺口4 | 用户可感知的"待清理"提醒 | 0% | 3 个触发入口 |

---

## 6. 不在此计划内的内容（交由后续）

以下能力已在外层 ADR 中规划为 v5.2，本轮不做：

- ❌ 跨项目经验迁移（v5.2: Active Discovery）
- ❌ 技能市场完善（v5.1: SkillMarket expansion，已部分实现）
- ❌ 智能推荐引擎（v5.2: Smart Recommendations）
- ❌ 路由透明度增强（`skillos-productization.md` 已覆盖）
- ❌ 质量评分驱动路由（`skillos-productization.md` Phase A P1 已覆盖）

---

*Generated: 2026-04-26 | Status: Draft | Author: VibeSOP analysis*
