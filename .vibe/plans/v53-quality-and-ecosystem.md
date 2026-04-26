# v5.3 品质筑基 + 生态收尾 — 从能用到好用

> **Status**: Draft
> **Date**: 2026-04-27
> **Based on**: 项目全景分析 + ROADMAP.md 剩余项 + 代码审查发现
> **Theme**: 停止加功能，专注做减法——精简代码、优化性能、清质量门、补齐最后两个生态功能
> **Related**: v51-skill-ecosystem-closure.md ✅ | v52-transparency-and-execution.md ✅

---

## 0. 诊断发现

### 0.1 核心数据

| 指标 | 当前 | 目标 | 差距 |
|------|------|------|------|
| Python 行数 | 52,581 | ~25,000 | 2.1× |
| Python 文件数 | 209 | ~150 | 1.4× |
| P95 延迟 | 225ms | <100ms | 2.3× |
| Lint 错误 | 34 (20 可自动修复) | 0 | 14 需手修 |
| 测试覆盖率 | 74% | >80% | +6% |

### 0.2 发现的数据冲突

`skill_cmd.py` 和 `skills_cmd.py` 各有独立的 `enable`/`disable`/`status` 命令，**写入不同的存储后端**：

```
vibe skill enable <id>    → .vibe/skills.json           (_save_skill_state)
vibe skills enable <id>   → .vibe/skills/auto-config.yaml (SkillConfigManager)
```

`SkillLoader.discover_all()` 只读 `auto-config.yaml`，意味着 `vibe skill enable` 的状态对路由系统**完全不可见**。这是一个可导致用户困惑的数据一致性缺陷。

### 0.3 发现的命令重叠

| 命令 | skill (lifecycle) | skills (storage) | 冲突? |
|------|-------------------|-------------------|-------|
| `enable` | ✅ 写 json | ✅ 写 yaml | **数据冲突** |
| `disable` | ✅ 写 json | ✅ 写 yaml | **数据冲突** |
| `status` | ✅ 单技能详情 | ✅ 存储总览 | 语义不同 |
| `list` | ✅ 状态列表 | ✅ 存储列表 | 语义不同 |

---

## 1. Phase A: 消除冗余 + 修复数据冲突（Week 1）

### Task A.1: 合并 skill_cmd → skills_cmd，统一存储后端（2天）

**问题**：两个模块有独立但重叠的命令集，且写入不同后端。

**方案**：
1. 将 `skill_cmd.py` 中独有的命令（`stale`, `end_check`）迁移到 `skills_cmd.py`
2. 删除 `skill_cmd.py` 中与 `skills_cmd.py` 重复的 `enable`/`disable`/`status`
3. `skill_cmd.py` 的 `enable`/`disable` 从 `_save_skill_state`（写 `.vibe/skills.json`）改为调用 `SkillConfigManager.update_skill_config`（写 `auto-config.yaml`）
4. `skill_cmd.py` 的 `list` 保留但去重——合并 `_load_skills` 的候选加载逻辑
5. 完成后删除 `skill_cmd.app` 的子 Typer 注册，`vibe skill` 命令统一走 `skills_app`

**影响文件**：
- `src/vibesop/cli/commands/skill_cmd.py` → 仅保留 `stale`, `end_check`, `list`
- `src/vibesop/cli/commands/skills_cmd.py` → 接管 `enable`/`disable`/`status` 主职
- `src/vibesop/cli/main.py` → 删除 `app.add_typer(skill_cmd.app, name="skill")`
- `src/vibesop/cli/subcommands/__init__.py` → 注册 `stale`, `end_check` 到 skills_app

**向后兼容**：
```bash
vibe skill enable <id>      # 保留，委托到 skills_app.enable
vibe skills enable <id>     # 保留（主实现）
vibe skill stale            # 保留
vibe skill end-check        # 保留
vibe skill list             # 保留
```

**验收标准**：
- [ ] `vibe skill enable <id>` 和 `vibe skills enable <id>` 写入同一后端
- [ ] 删除 `.vibe/skills.json` 写入逻辑（只保留 `auto-config.yaml`）
- [ ] `skill_cmd.py` 从 240 行精简到 ~100 行（只保留 stale/end_check/list）
- [ ] 现有路由过滤正常工作

---

### Task A.2: Adapter 去重 — 消除 _find_skill_content / _normalize_skill_type 重复（1天）

**现状**：三个 Adapter 中各有相同的 `_find_skill_content` 和 `_normalize_skill_type` 方法。

**方案**（v5-quality-sprint Task 1.2 方案）：
1. 将共用方法抽取到 `adapters/_shared.py`
2. `claude_code.py`, `opencode.py`, `kimi_cli.py` 改为调用 `_shared`

**验收标准**：
- [ ] 三个 Adapter 不再有重复的 `_find_skill_content`（减少 ~120 行）
- [ ] 三个 Adapter 不再有重复的 `_normalize_skill_type`（减少 ~60 行）

---

### Task A.3: lint 清零 + coverage 上 80%（1天）

**lint**：
```bash
uv run ruff check --fix        # 自动修复 20 个
# 手动处理剩余 14 个（PTH201, SIM105, SIM108 等）
```

**coverage**：
- 当前 74% → 目标 80%（+6%）
- 优先覆盖：`skill_cmd.py` stale/end_check、`suggestion_collector.py`、`retention.py` archive 事件
- 新增 ~15 个测试用例

**验收标准**：
- [ ] `ruff check` 输出 0 errors
- [ ] `pytest --cov=src/vibesop --cov-report=term --cov-fail-under=80` 通过

---

### Task A.4: 代码精简 — 移除无用文件（0.5天）

**扫描**：
```bash
# 检查 .vibe/dist/ 下 83 个重复 README 是否需要
# 检查 memory/ 下 3 个 md + 1 yaml 是否被代码引用
# 检查 docs/ 下 63 个 md 中是否有过期/重复文档
```

**验收标准**：
- [ ] 目标：总 Python 行数从 52,581 → ~45,000（减少 ~15%）
- [ ] 无功能退化

---

## 2. Phase B: 性能优化（Week 2）

### Task B.1: Hot-path 缓存优化（2天）

**现状**：P95 225ms，瓶颈在 AI Triage 层（~100ms LLM 调用）和候选加载。

**方案**：

#### B.1a: 候选预加载 + 增量更新
```python
# SkillLoader: 缓存已加载候选，避免每次 route() 都 rglob + parse
class SkillLoader:
    _candidate_cache: dict[str, LoadedSkill] = {}
    _cache_mtime: float = 0.0

    def discover_all(self, force_reload: bool = False):
        # 仅在文件修改时间变化时重新扫描
        if not force_reload and self._is_cache_fresh():
            return self._candidate_cache
        ...
```

#### B.1b: AI Triage 层 快速降级
```python
# 场景层（Layer 2）命中 ≥ 0.85 时跳过 AI Triage（~100ms 节省）
class UnifiedRouter:
    def _execute_layers(self, ...):
        scenario_result = self._run_scenario_layer(query, candidates)
        if scenario_result and scenario_result.confidence >= 0.85:
            # 高置信度场景匹配，跳过 LLM
            ai_triage_skipped = True
        else:
            ai_result = self._run_ai_triage_layer(query, candidates)
```

#### B.1c: 延迟加载重依赖
```python
# sentence_transformers 仅在 embedding 层首次调用时加载
class InstinctLearner:
    def _embedding_enabled(self):
        if self._embedding_model is None:
            try:
                self._embedding_model = SentenceTransformer(...)
            except ImportError:
                return False
        return True
    # ✅ 已实现！检查确认
```

**验收标准**：
- [ ] P95 延迟从 225ms → <150ms（保守目标）
- [ ] 场景层高置信匹配时跳过 LLM，延迟 <10ms
- [ ] 缓存命中率 > 80%

---

### Task B.2: CLI 响应优化（1天）

**现状**：`vibe skills list` 每次重新加载所有技能 + 评估数据。

**方案**：
- 评估数据懒加载（仅在 `--show-status` 或 `--all` 时加载）
- 技能列表缓存（`.vibe/cache/skills_index.json`）

**验收标准**：
- [ ] `vibe skills list` 从 ~500ms → <200ms
- [ ] `vibe route` 热路径无退化

---

## 3. Phase C: 技能评分体系（v5.1 唯一缺失）（Week 3）

### Task C.1: Rating/Review 系统（2天）

**新增文件**: `src/vibesop/core/skills/ratings.py`

```python
@dataclass
class SkillRating:
    skill_id: str
    user_id: str  # "local" by default
    score: int  # 1-5 stars
    review: str = ""
    created_at: str = ""  # ISO timestamp

class SkillRatingStore:
    """Persistent rating & review storage for skills."""
    STORE_PATH = Path(".vibe/ratings.jsonl")

    def rate(self, skill_id: str, score: int, review: str = "") -> SkillRating: ...
    def get_ratings(self, skill_id: str) -> list[SkillRating]: ...
    def get_avg_score(self, skill_id: str) -> float: ...
    def get_top_rated(self, limit: int = 10) -> list[tuple[str, float]]: ...
```

**CLI 集成**：
```bash
$ vibe skills rate gstack/review 5 "Excellent code review skill"
✓ Rating saved: 5/5

$ vibe skills ratings gstack/review
⭐ 4.7/5 (3 reviews)
  • 5/5 — "Excellent code review skill" (2026-04-27)
  • 4/5 — "Good but slow" (2026-04-25)
  • 5/5 — "Best review skill" (2026-04-20)
```

**验收标准**：
- [ ] `vibe skills rate <id> <1-5>` 持久化评分
- [ ] `vibe skills ratings <id>` 展示评分历史和平均值
- [ ] `vibe skills report` 评分维度纳入 quality_score

---

### Task C.2: 兼容性矩阵（1天）

**修改**: `src/vibesop/core/skills/external_loader.py`

```python
@dataclass
class CompatibilityMatrix:
    skill_id: str
    platforms: dict[str, str]  # {"claude-code": "native", "opencode": "partial", ...}
    tested_versions: dict[str, str]  # {"claude-code": "1.0.37+", "opencode": "0.8+"}

class CompatibilityChecker:
    def check(self, skill_id: str, platform: str) -> tuple[bool, str]: ...
```

**CLI**：
```bash
$ vibe skills compat gstack/review
Platform         Support    Min Version
claude-code      ✅ native   1.0.37+
opencode         ⚠️ partial  0.8+
kimi-cli         ❌ unsupported
```

从 SKILL.md frontmatter 的 `supported_platforms` 字段读取兼容性数据。

**验收标准**：
- [ ] 从 SKILL.md `supported_platforms` 解析兼容性
- [ ] `vibe skills compat <id>` 展示矩阵

---

## 4. Phase D: 智能推荐（v5.2 收尾）（Week 4）

### Task D.1: 基于项目类型的推荐（1.5天）

**修改**: 新增 `src/vibesop/core/skills/recommender.py`

```python
class SkillRecommender:
    # 项目类型 → 推荐技能的映射
    STACK_RECOMMENDATIONS = {
        "python": ["superpowers/tdd", "gstack/review", "superpowers/refactor"],
        "javascript": ["gstack/review", "gstack/qa", "superpowers/tdd"],
        "rust": ["gstack/review", "superpowers/optimize"],
        "go": ["gstack/review", "superpowers/architect"],
    }

    def recommend_for_project(self, project_root: Path) -> list[SkillRecommendation]:
        """基于项目技术栈推荐技能"""
        project_info = self._analyze_project(project_root)
        stack = project_info.get("primary_language", "unknown")
        installed = self._get_installed_skills()
        recommended = [s for s in self.STACK_RECOMMENDATIONS.get(stack, [])
                       if s not in installed]
        return recommended
```

**CLI**：
```bash
$ vibe skills recommended
📋 Recommended for this Python project:

1. superpowers/tdd — Test-driven development workflow
   [install] [info] [dismiss]

2. gstack/review — Pre-landing PR review
   Already installed ✓

3. superpowers/refactor — Systematic code refactoring
   [install] [info] [dismiss]
```

**验收标准**：
- [ ] `vibe skills recommended` 基于项目类型推荐
- [ ] 已安装技能标记为 ✓
- [ ] 一键安装：`vibe skills recommended --install`

---

### Task D.2: 协同过滤推荐（1天）

```python
class SkillRecommender:
    def collaborative_filter(self) -> list[SkillRecommendation]:
        """'Users who installed X also installed Y' based on local usage."""
        # 简单版：基于已安装技能包的共现关系
        installed_packs = self._get_installed_packs()
        # 如果有人装了 gstack + superpowers，当前只装了 gstack → 推荐 superpowers
        ...
```

**验收标准**：
- [ ] `vibe skills recommended --collaborative` 展示协同过滤推荐
- [ ] 推荐理由可见："users who installed gstack also installed superpowers"

---

## 5. 执行顺序

```
Week 1: Phase A — 消除冗余 + 修复数据冲突
  Day 1-2:  Task A.1 合并 skill_cmd → skills_cmd，统一存储
  Day 3:    Task A.2 Adapter 去重
  Day 4:    Task A.3 lint 清零 + coverage 80%
  Day 5:    Task A.4 代码精简

Week 2: Phase B — 性能优化
  Day 6-7:  Task B.1 Hot-path 缓存 + AI Triage 快速降级
  Day 8:    Task B.2 CLI 响应优化

Week 3: Phase C — 技能评分体系
  Day 9-10: Task C.1 Rating/Review 系统
  Day 11:   Task C.2 兼容性矩阵

Week 4: Phase D — 智能推荐 + 回归
  Day 12-13: Task D.1 基于项目类型的推荐
  Day 14:    Task D.2 协同过滤推荐
  Day 15:    回归测试 + ROADMAP 终版更新
```

**并行机会**：
- Phase A + Phase C 无依赖，可并行
- Phase B 依赖 Phase A（去重后性能测量才准确）
- Phase D 依赖 Phase C（推荐系统使用评分数据）

---

## 6. 验收总览

| 阶段 | 关键交付 | 度量 |
|------|---------|------|
| A | 合并 skill_cmd → skills_cmd，统一存储 | 命令数减少 3 个重复，数据一致性修复 |
| A | Adapter 去重 | ~180 行冗余代码消除 |
| A | Lint + Coverage | 0 errors, >80% |
| A | 代码精简 | 52,581 → ~45,000 行 |
| B | Hot-path 缓存 | P95 225ms → <150ms |
| B | AI Triage 快速降级 | 高置信度场景 <10ms |
| C | Rating/Review | `vibe skills rate/ratings` 可用 |
| C | 兼容性矩阵 | `vibe skills compat` 可用 |
| D | 智能推荐 | `vibe skills recommended` 可用 |
| D | 协同过滤 | `--collaborative` 可展示 |

---

## 7. 不做的事

| 事项 | 理由 |
|------|------|
| Web UI / IDE 集成 | Backlog 中，用户基数不足 |
| 技能执行引擎 | 违反 SkillOS 边界 |
| 新 LLM 提供商 | Anthropic/OpenAI/Ollama 已覆盖 |
| 重写架构 | 功能完备，收益 < 成本 |
| 跨项目经验自动迁移 | v5.2 Active Discovery，需更多使用数据 |

---

*Generated: 2026-04-27 | Status: Draft*
