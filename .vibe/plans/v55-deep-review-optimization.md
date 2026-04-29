# v5.5 深度评审驱动优化 — 从能用到可靠

> **Status**: Draft
> **Date**: 2026-04-29
> **Based on**: 深度项目分析（PHILOSOPHY + version_05.md + ROADMAP + 全量代码审查）
> **Theme**: 清偿技术债 — 统一版本、填补测试鸿沟、精简 API、修复线程安全
> **Related**: v53-quality-and-ecosystem.md ✅ | v52-transparency-and-execution.md ✅

---

## 0. 诊断摘要

### 0.1 核心发现

| 指标 | 当前 | 目标 | 差距 |
|------|------|------|------|
| 版本号一致性 | 5 处不一致 | 1 处真实源 | 4 处待修 |
| 测试覆盖率 | 20% | 75% | **55 个百分点** |
| 路由 API 层级 | `_route()` → `route()` → `orchestrate()` | 1 个公开入口 | 2 层冗余 |
| 纯路由 P95 | ~50ms | <100ms | ✅ |
| LLM Triage P95 | ~220ms | <300ms | ✅ |
| Lint 错误 | 0 (有限规则集) | 0 | ✅ |
| Python 文件数 | 231 | ~180 | 1.3× 膨胀 |

### 0.2 本次评审 vs 上次评审（v5.3）

| 维度 | v5.3 发现 | 本次发现 | 变化 |
|------|----------|---------|------|
| 测试覆盖率 | 74% (声明) | **20%** (实测) | 严重恶化 / 数据不实 |
| 技能数据冲突 | `skill_cmd` vs `skills_cmd` | （已在 v5.3 修复） | ✅ |
| 版本号混乱 | 未发现 | **5 处不一致** | 🔴 新增 |
| 路由 API 冗余 | 未深度审查 | **3 层间接** | 🔴 新发现 |
| 线程安全 | 未评估 | **跨组件锁不协调** | 🟡 新增 |
| 候选缓存不一致 | 未审查 | **可能返回过期数据** | 🟡 新增 |

### 0.3 问题优先级总览

| # | 问题 | 严重度 | 位置 | 影响 |
|---|------|--------|------|------|
| P0-1 | 测试覆盖率 20% vs 75% 硬性要求 | 🔴 致命 | `pyproject.toml:233` | CI 形同虚设，重构无安全保障 |
| P0-2 | `_version.py:13` PATCH=2 vs `pyproject.toml:3` version="5.3.3" | 🔴 致命 | 2 处 | 运行时版本号与打包版本冲突 |
| P0-3 | PHILOSOPHY.md 版本标注 5.2.0/4.4.0 矛盾 | 🔴 致命 | 文档 | 信任信号，误导贡献者 |
| P1-1 | `route()` / `_route()` / `orchestrate()` 三层间接 | 🟡 高 | `unified.py` | API 混乱，deprecated 方法仍为核心依赖 |
| P1-2 | 长查询跳过 matcher pipeline 后无 AI Triage 回退 | 🟡 高 | `unified.py:378-391` | 可能出现无技能匹配的静默失败 |
| P1-3 | `get_cached_candidates()` 持久化缓存过期不一致 | 🟡 高 | `candidate_manager.py:173-176` | 新增技能可能不被路由识别 |
| P2-1 | `record_usage()` 缓冲区满前崩溃丢数据 | 🟢 中 | `candidate_manager.py:253` | 使用统计数据不准确 |
| P2-2 | `result_mixin.py` 重复初始化 SkillRecommender | 🟢 中 | `result_mixin.py:131-139, 167-174` | 代码重复 |
| P2-3 | `_to_orchestration_result` 语义错误 | 🟢 中 | `orchestration_mixin.py:52-62` | FALLBACK 标记为 SINGLE |
| P2-4 | 20 路线间隔硬编码 | 🟢 低 | `main.py:752` | 不可配置 |
| P2-5 | `_handle_orchestrated_result` 函数过长 | 🟢 低 | `main.py:429-527` | 可维护性 |

---

## 1. Phase A: 治理修复（Week 1）

### Task A.1: 统一版本号为单一真实源（1 天）

**问题**：版本号分散在 5 处且不一致：
- `pyproject.toml:3` — `version = "5.3.3"`
- `src/vibesop/_version.py:15` — `PATCH = 2` (产生 `5.3.2`)
- `docs/PHILOSOPHY.md:3` — `版本: 5.2.0`，末尾 `版本: 4.4.0`
- `docs/architecture/ARCHITECTURE.md:3` — `Version: 5.3.0`
- `docs/PROJECT_STATUS.md:3` — `Version: 5.3.0`

**方案**：

1. **`pyproject.toml` 为唯一权威源**
   ```python
   # src/vibesop/_version.py → 改为从 pyproject.toml 读取
   import importlib.metadata
   __version__ = importlib.metadata.version("vibesop")
   ```

2. **删除硬编码的 `MAJOR/MINOR/PATCH`**（或保留为只读属性，从 `__version__` 解析）

3. **文档版本号集中管理**：在 `docs/` 下创建 `_version.txt`，所有文档通过 CI 脚本自动替换 `> **版本**: X.Y.Z` 占位符

4. **CI 增加版本校验 job**：
   ```bash
   # .github/workflows/version-check.yml
   python -c "import vibesop; assert vibesop.__version__ == ..."
   grep -r "版本:" docs/ | diff - <(expected)
   ```

**影响文件**：
- `src/vibesop/_version.py` — 简化为单行 `__version__ = importlib.metadata.version("vibesop")`
- `docs/PHILOSOPHY.md:3, 431-432` — 统一为 `5.3.2`
- `docs/architecture/ARCHITECTURE.md:3` — 统一为 `5.3.2`
- `docs/PROJECT_STATUS.md:3, 268` — 统一为 `5.3.2`（同时删除末尾重复的 `Last Updated`）
- `docs/ROADMAP.md:3` — 统一为 `5.3.2`
- `.github/workflows/` — 新增 `version-check.yml`

**验收标准**：
- [ ] `python -c "import vibesop; print(vibesop.__version__)"` 输出 `5.3.3`
- [ ] `grep -rn "版本:" docs/` 所有文档一致
- [ ] `grep -rn "Version:" docs/` 所有文档一致
- [ ] CI 版本校验 job 通过

---

### Task A.2: 修复 PHILOSOPHY.md 自相矛盾（0.5 天）

**问题**：
- 第 3 行标注 `版本: 5.2.0`
- 第 431-432 行标注 `版本: 4.4.0` / `更新时间: 2026-04-26`
- 与全局版本 `5.3.2` 不符

**方案**：
1. 头部和尾部版本号统一为 `5.3.2`
2. 删除第 431-432 行（与头部重复的元数据）
3. 第 390 行「生产流程中执行由 AI Agent 完成」与 CLI 实际能力不匹配 → 更新为准确描述

**影响文件**：
- `docs/PHILOSOPHY.md` — 仅元数据修复，不改哲学内容

**验收标准**：
- [ ] `grep "版本:" docs/PHILOSOPHY.md` 唯一匹配且值为 `5.3.2`
- [ ] 执行能力说明与 CLI 实际命令一致

---

## 2. Phase B: 测试基础设施重建（Week 1-2）

### Task B.1: 测试覆盖率从 20% 提升到 75%（主要工作 5 天）

**问题**：2202 个测试但只覆盖 20% 的语句。这意味着大量测试是浅层测试（仅测试 __init__、数据类序列化），核心路由逻辑未被覆盖。

**根因分析**：
1. 2202 个测试中大量为 baseline 测试（空测试 / 仅测试 import / 仅测试 Pydantic schema 反序列化）
2. `UnifiedRouter.orchestrate()` 的 real 路径无法测试（依赖 LLM API）
3. Mixin 架构使 Mock 成本高（需要 setup 整个 Router 对象）
4. `tests/` 中「test_exist」类测试占比过高

**方案（3 阶段交付）**：

**阶段 B.1.1 — 覆盖率增量 20% → 40%（2 天）**

优先为纯逻辑模块补测试（无需 LLM 依赖）：

| 模块 | 当前覆盖 | 目标 | 测试内容 |
|------|---------|------|---------|
| `degradation.py` | 未知 | >90% | 4 级门控的边界条件 |
| `result_mixin.py` | 未知 | >70% | `_build_match_result` / `_build_fallback_result` |
| `orchestration_mixin.py` | 未知 | >70% | `_to_orchestration_result` 各种 mode |
| `candidate_manager.py` | 未知 | >60% | `filter_routable` / `_get_skill_source` |
| `confirmation.py` | 未知 | >80% | `_needs_confirmation` 三态逻辑 |

**阶段 B.1.2 — 覆盖率增量 40% → 60%（2 天）**

引入 Router Mock 方法：

```python
# tests/conftest.py — 新增 fixtures
@pytest.fixture
def mock_llm_client():
    """可预设响应的 Mock LLM"""
    class MockLLM:
        responses: list[str] = []
        def call(self, prompt, max_tokens=100, temperature=0.1):
            return type("Resp", (), {"content": self.responses.pop(0)})()
        def configured(self):
            return True
    return MockLLM()

@pytest.fixture
def router_with_mock_llm(mock_llm_client, tmp_path):
    """注入 Mock LLM 的 Router"""
    mock_llm_client.responses = [
        '{"matched_skills": [{"skill_id": "gstack/review", "confidence": 0.85}]}'
    ]
    r = UnifiedRouter(project_root=tmp_path)
    r.set_llm(mock_llm_client)
    return r
```

覆盖路径：
- `orchestrate()` 的 SINGLE 路径（无 LLM 调用）
- `orchestrate()` 的 DECOMPOSITION → PLAN_BUILDING 路径（注入 Mock LLM）
- `_should_use_keyword_routing()` 的长/短查询分支
- `_try_layers()` 的 early exit vs full pipeline

**阶段 B.1.3 — 覆盖率增量 60% → 75%（1 天）**

- 为 `candidate_manager.py` 补完遗漏路径（`_check_reload_needed` / `_flush_usage_buffer`）
- 为 `cache.py` / `circuit_breaker.py` / `conflict.py` 补测试
- 修复 `coverage.py` 的 `fail_under = 75` 使其在 CI 中强制执行

**关键决策**：是否在 CI 中强制执行 `fail_under = 75`？

```
方案 A: 立即强制 → CI 会失败，阻塞所有 PR
方案 B: 渐进强制 → 先设 fail_under = 40，7 天后 55，14 天后 75 ⭐ 推荐
```

选方案 B。修改 `pyproject.toml:233`:
```toml
[tool.coverage.report]
fail_under = 40  # v5.5 第一期目标，逐步提升到 75
```

**影响文件**：
- `tests/unit/core/routing/` — 新增 `test_degradation.py`、`test_orchestration_mixin.py`、`test_candidate_manager_filtering.py`
- `tests/conftest.py` — 新增 `mock_llm_client`、`router_with_mock_llm` fixtures
- `tests/unit/core/routing/test_unified_router.py` — 新增 orchestration 路径测试
- `pyproject.toml:233` — `fail_under: 40` (渐进)

**验收标准**：
- [ ] 覆盖率 ≥ 40%（Phase B.1.1）
- [ ] 覆盖率 ≥ 60%（Phase B.1.2）
- [ ] 覆盖率 ≥ 75%（Phase B.1.3）
- [ ] `pytest --cov --cov-fail-under=75` 在 CI 中通过

---

## 3. Phase C: 路由架构修缮（Week 2）

### Task C.1: 精简路由 API 三层为两层（1 天）

**问题**：`_route()` → `route()` → `orchestrate()` 三层，`route()` 已标记 deprecated 但 `_route()` 仍然是 `orchestrate()` 的核心依赖。

```
当前调用链:
  CLI route → router.orchestrate() → router._route() → _try_layers()
  CLI orchestrate → router.orchestrate() → router._route() → _try_layers()
  (deprecated) router.route() → router._route() → _try_layers()
```

**方案**：

1. **将 `route()` 的 deprecation warning 改为 silence**
2. **将 `_route()` 重命名为 `_single_skill_route()`**，明确其职责
3. **`orchestrate()` 内部调用 `_single_skill_route()`**
4. **标记 `route()` 为 v6.0 移除**

```python
# unified.py — 重构后
class UnifiedRouter:
    def orchestrate(self, query, candidates=None, context=None, callbacks=None):
        # Fast path: single-skill routing
        single_result = self._single_skill_route(query, candidates, context)
        # ... multi-intent detection ...
    
    def _single_skill_route(self, query, candidates=None, context=None):
        """Internal: route query to best matching skill (single-skill mode)."""
        # 原 _route() 逻辑
    
    def route(self, query, candidates=None, context=None):
        """Deprecated. Use orchestrate() instead. Will be removed in v6.0."""
        warnings.warn("...", DeprecationWarning, stacklevel=2)
        return self._single_skill_route(query, candidates, context)
```

**影响文件**：
- `src/vibesop/core/routing/unified.py:260-313` — 重命名 `_route` → `_single_skill_route`
- 搜索引用 `_route()` 的所有文件并更新

**验收标准**：
- [ ] `grep -rn "\._route(" src/` 无匹配
- [ ] `grep -rn "_single_skill_route" src/` 存在且用于所有调用
- [ ] 现有 2202 个测试全部通过
- [ ] `router.route()` 向后兼容（保留 deprecated）

---

### Task C.2: 修复长查询路由回退隐患（0.5 天）

**问题** (`unified.py:378-391`)：
```python
else:
    # Long query: skip keyword-based layers, use LLM semantic triage
    match, detail = _layers.try_ai_triage_layer(
        self, query, candidates, context, force=True
    )
    ...
    if match and match.confidence >= self._config.min_confidence:
        ...
        return ...
    # 如果 AI Triage 返回 None 且不抛异常 → 直接 fall through 到 None
    # → _try_layers 返回 None → _finalize_no_match
```

**方案**：当长查询 AI Triage 不可用或返回 None 时，回退到 matcher pipeline（而非直接进入 FALLBACK_LLM）：

```python
else:
    # Long query: prefer LLM triage, but fall back to matchers
    match, detail = _layers.try_ai_triage_layer(
        self, query, candidates, context, force=True
    )
    routing_path.append(RoutingLayer.AI_TRIAGE)
    layer_details.append(detail)
    if match and match.confidence >= self._config.min_confidence:
        self._record_layer(RoutingLayer.AI_TRIAGE)
        return self._build_match_result(...)
    
    # Fallback: still try matcher pipeline for long queries
    primary, alternatives, detail = _pipeline.run_matcher_pipeline(
        self, query, candidates, context, collect_rejected=True
    )
    routing_path.append(detail.layer)
    layer_details.append(detail)
    if primary and primary.confidence >= self._config.min_confidence:
        self._record_layer(detail.layer)
        return self._build_match_result(...)
```

**影响文件**：
- `src/vibesop/core/routing/unified.py:378-392`

**验收标准**：
- [ ] 长查询（>5 chars，无 LLM key）+ keyword/tfidf 可匹配 → 返回 matcher 结果而非 FALLBACK
- [ ] 新增 `test_long_query_fallback_to_matchers` 测试

---

### Task C.3: 修复 `_to_orchestration_result` 语义错误（0.25 天）

**问题** (`orchestration_mixin.py:52-62`)：`primary=None` 时仍返回 `mode=SINGLE`

**方案**：
```python
def _to_orchestration_result(self, result: RoutingResult, query: str) -> OrchestrationResult:
    mode = (
        OrchestrationMode.SINGLE
        if result.primary is not None
        else OrchestrationMode.FALLBACK
    )
    return OrchestrationResult(
        mode=mode,
        ...
    )
```

**影响文件**：
- `src/vibesop/core/routing/orchestration_mixin.py:52-62`

---

### Task C.4: 消除 result_mixin.py 重复代码（0.25 天）

**方案**：提取 `_get_skill_recommender()` 方法：
```python
def _get_skill_recommender(self) -> Any:
    host = cast("_ResultHost", self)
    if host._skill_recommender is None:
        from vibesop.integrations.skill_recommender import SkillRecommender
        host._skill_recommender = SkillRecommender()
    return host._skill_recommender
```

**影响文件**：
- `src/vibesop/core/routing/result_mixin.py:131-139, 167-174`

---

## 4. Phase D: 缓存与线程安全（Week 2-3）

### Task D.1: 修复候选缓存不一致（1 天）

**问题**：`get_cached_candidates()` 可能从持久化缓存返回过期数据，而 `get_candidates()` 每次都从 `SkillLoader.discover_all()` 重新加载。如果用户装了一个新技能但无 `.skills_reload` 标记触发，旧缓存返回的数据缺新技能。

**方案**：
1. 持久化缓存增加 per-skill-file hash（而非只 hash 目录路径）
2. 或者：缩短 `_RELOAD_CHECK_INTERVAL`（当前 5 秒 → 改为 30 秒的 mtime 检查）
3. 或者：每次路由前通过 stats 检查路径 mtime，仅在 mtime 变化时刷新

**推荐方案 3**（最轻量，不会增加每次路由开销）：
```python
def _should_check_reload(self) -> bool:
    """Rate-limited: probe filesystem marker + search path mtimes every N seconds."""
    import time
    now = time.monotonic()
    if now - self._last_reload_check < self._RELOAD_CHECK_INTERVAL:
        return False
    self._last_reload_check = now
    
    # Check marker file
    if self._check_reload_needed():
        return True
    
    # Check if any search path mtime changed
    for sp in self._search_paths:
        if sp.exists():
            try:
                mtime = sp.stat().st_mtime
                if mtime != self._path_mtimes.get(str(sp), 0):
                    self._path_mtimes[str(sp)] = mtime
                    return True
            except OSError:
                continue
    return False
```

**影响文件**：
- `src/vibesop/core/routing/candidate_manager.py:150-163, 184-198`

**验收标准**：
- [ ] 安装新技能包后不手动触发 `.skills_reload` → 下次路由（30s 内）候选列表包含新技能
- [ ] 路径未变化时不触发不必要的全量 reload

---

### Task D.2: 修复 record_usage 数据丢失（0.5 天）

**问题**：缓冲区每 10 条才 flush，异常退出丢 ≤9 条。

**方案**：非关键路径，容忍部分丢失（usage_stats 本身就是近似统计）。但改为：

1. 在 `router.__del__()` 中调用 `_flush_usage_buffer()`
2. 或在 `UnifiedRouter.__init__` 注册 `atexit` handler：
```python
import atexit
atexit.register(self._candidate_manager._flush_usage_buffer)
```

**影响文件**：
- `src/vibesop/core/routing/unified.py:114` — 在 `__init__` 末尾注册
- `src/vibesop/core/routing/candidate_manager.py:253` — `_flush_usage_buffer` 需为幂等

---

### Task D.3: 线程安全审计与修复（1 天）

**问题**：`_stats_lock`（router 层）和 `_cache_lock`（candidate manager 层）各自独立，跨组件无协调。

**低风险路径**（当前影响小，因为多数调用是单线程 CLI）：
- `orchestrate()` → `_single_skill_route()` → `get_cached_candidates()` (获取 `_cache_lock`)
- `_build_match_result()` → `record_usage()` (获取 `_usage_buffer`)
- `record_usage()` 内部可能触发 `_flush_usage_buffer()` → `SkillConfigManager.update_skill_config()` (IO)

**方案**：
1. 为 `record_usage` 和 `get_cached_candidates` 同时获取的路径增加 `threading.local()` 隔离
2. 或者（更简单）：在 router 级别增加一个 coarse lock，整个 `orchestrate()` 调用串行化

```python
# unified.py — router level serialization
self._route_lock = threading.Lock()

def orchestrate(self, query, ...):
    with self._route_lock:
        # existing logic
```

**影响文件**：
- `src/vibesop/core/routing/unified.py:114, 525-712`

---

## 5. Phase E: 可配置化与轻量重构（Week 3）

### Task E.1: 20 路线间隔配置化（0.25 天）

**问题** (`main.py:752`): `check_interval = counter.get("check_interval", 20)` 硬编码默认值。

**方案**：
```python
# 从 config 读取
interval = getattr(router._config, "stale_check_interval", 20)
```

或在路由配置中新增字段 `stale_check_interval: int = 20`。

**影响文件**：
- `src/vibesop/cli/main.py:752`
- `src/vibesop/core/config/routing_config.py` — 新增配置字段

---

### Task E.2: 拆分 `_handle_orchestrated_result`（0.5 天）

**问题**：函数 ~100 行，混合了确认、编辑、执行、保存逻辑。

**方案**：拆分为 3 个函数：
- `_orchestration_confirmation_flow()` — 纯确认交互
- `_orchestration_plan_execution()` — 执行路径（`_execute_plan_interactive`）
- `_orchestration_post_process()` — 保存 plan + 收集反馈

**影响文件**：
- `src/vibesop/cli/main.py:429-527`

---

## 6. 执行时间表

| 周 | Phase | 产出 | 测试覆盖率 |
|----|-------|------|-----------|
| W1 | A + B.1.1 | 版本统一 + 核心模块测试 | 20% → 40% |
| W1-2 | B.1.2 | Router Mock + 编排路径测试 | 40% → 60% |
| W2 | C.1-C.4 + B.1.3 | API 精简 + 路由回退修复 + 最后测试 | 60% → **75%** |
| W2-3 | D.1-D.3 | 缓存 + 线程安全 | 75% (维护) |
| W3 | E.1-E.2 + 验收 | 配置化 + 轻量重构 | 75% (维护) |

**总计**: 3 周，1 人全职

---

## 7. 成功指标

| 指标 | 当前 | 目标 |
|------|------|------|
| 版本号一致性 | 5 处不一致 | **1 处权威源，0 处不一致** |
| 测试覆盖率 | 20% | **≥75%** |
| CI fail_under | 无效（未强制执行） | **强制执行 75** |
| 路由 API 入口 | `_route/route/orchestrate` 3 层 | **`orchestrate` 唯一公开 + `_single_skill_route` 内部** |
| 路由回退安全 | 长查询可能静默失败 | **长查询也有 matcher pipeline 回退** |
| 候选缓存时效 | 最长 5 秒过期 + 标记触发 | **30 秒内 mtime 自动检测刷新** |
| 线程安全 | 无协调 | **router 级 coarse lock** |

---

## 附录 A: 不需要立即处理的项目（已记录不计划）

以下问题记录但**不纳入本次计划**：

| 问题 | 理由 |
|------|------|
| PHILOSOPHY.md「发现>执行」与 CLI 执行能力矛盾 | 哲学层问题，需要 v6.0 重新定位讨论 |
| v4.x-v5.x 版本语义模糊 | 历史遗留，v6.0 统一解决 |
| `skill_cmd` vs `skills_cmd` 数据冲突 | 已在 v5.3 修复 |
| 文档 100+ md 文件精简 | 低优先级，独立计划 |

## 附录 B: 需要讨论的开放决策

1. **PHILOSOPHY.md 的「我们不做什么」是否需要更新？**
   - 当前 CLI 有完整的 interactive execution mode，与「VibeSOP 不是执行器」相悖
   - 建议：要么（a）承认 VibeSOP 提供轻量级开发者执行能力（保留现状，更新哲学说明），要么（b）移除所有执行相关代码（回归纯路由工具）

2. **`route()` deprecated 是否直接删除（而非标记）？**
   - 当前 `route()` 已 deprecated 但无明确删除版本
   - 建议：v5.5 保持 deprecated + silence warning，v6.0 移除

---

*Generated by 深度项目分析 (2026-04-29)*
