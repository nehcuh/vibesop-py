# VibeSOP 评审发现汇总 (Optimization Findings)

> **来源**: 深度项目分析 (2026-04-28)
> **评审范围**: 架构、代码质量、测试覆盖、性能、文档一致性
> **状态**: 待处理

---

## 🔴 P0 — 阻塞性问题 (影响核心功能可靠性)

### P0.1 编排层 `orchestrate()` 零测试覆盖
- **影响**: 多意图检测、任务分解、执行计划——这些 v4.4/v5.x 核心特性几乎无验证
- **证据**: `unified.py` 覆盖率 14%，`orchestrate()` 方法无直接测试
- **风险**: 高——用户-facing 功能未经测试

### P0.2 `route()` 废弃但仍是事实标准
- **现象**: `route()` 标记 deprecated，但内部调用、测试、文档示例仍大量使用
- **文件**: `slash_commands.py:313`, `agent/__init__.py:552`, 所有 E2E 测试
- **风险**: 中——API 信号混乱，技术债累积

### P0.3 全量测试超时
- **现象**: `pytest` 在 300s 被 kill
- **根因**: 昂贵的 fixtures、文件 I/O、缺乏测试隔离
- **风险**: 高——无法运行 CI/CD

### P0.4 LLM 工厂测试失败 (4 tests)
- **文件**: `tests/llm/test_llm_factory.py`
- **失败**: `test_create_provider_invalid` 等 4 个测试
- **根因**: provider 默认值/验证逻辑变更后测试未同步

---

## 🟠 P1 — 架构问题 (影响长期可维护性)

### P1.1 `UnifiedRouter` God Class (1,284 行)
- **问题**: 同时处理路由、会话、LLM、预过滤、冲突解决、降级、推荐、分析
- **理想**: 每个 Layer 是独立 Strategy，Pipeline 组合
- **现状**: `_route()` 215 行，条件分支嵌套

### P1.2 循环依赖 → 方法内延迟导入
- **数量**: `unified.py` 中数十个方法内 import
- **臭味**: 相同导入重复出现（如 `SkillRecommender` 在 `_build_match_result` 中导入两次）
- **理想**: 模块顶部导入，清晰的依赖图

### P1.3 Mixin 边界模糊
- **文件**: `orchestration_mixin.py`
- **问题**: 6 处连续 `# type: ignore[attr-defined]`，`getattr(self, "_llm", None)`
- **理想**: Mixin 通过 Protocol/ABC 声明所需接口

### P1.4 CLI 每次命令新建 `UnifiedRouter`
- **问题**: Matcher 重复预热、Embedding 模型重复加载、Candidates 重新加载
- **影响**: 每次 CLI 调用都有显著启动开销

---

## 🟡 P2 — 代码质量问题 (影响可读性和健壮性)

### P2.1 裸 `except Exception` (30 处)
- **高密度**: `status_cmd.py` 9 处，`tips.py` 4 处
- **核心逻辑**: `candidate_manager.py`, `orchestration_mixin.py`, `retention.py`
- **后果**: 错误静默吞掉，调试困难

### P2.2 生产代码中的调试 `print()` (9 处)
- **LLM 模块**: `openai.py`, `anthropic.py`, `ollama.py` — 响应直接打印到 stdout
- **破坏**: JSON 输出被污染（2026-04-28 刚修复类似问题）

### P2.3 重复深合并实现 (3 处)
- `core/config/manager.py:365-420`
- `utils/helpers.py:158`
- `builder/overlay.py:195-198`

### P2.4 死代码
- `cli/main.py:730-735` — `return` 后的不可达代码
- `llm_config.py:417` — 获取 requirements 后立刻丢弃

### P2.5 类型安全压制
- `unified.py` 文件顶部全局 `# pyright: ignore[reportArgumentType]`
- 24+ 处 `# type: ignore` / `# noqa`

---

## 🟢 P3 — 性能问题

### P3.1 `_build_match_result` 重复获取 candidates
- **位置**: `unified.py:608, 646`
- **修复**: 一次获取，复用

### P3.2 `get_parallel_groups()` 浪费 dict 创建
- **位置**: `models.py:408`
- **修复**: 移除未使用的 dict comprehension

### P3.3 `_enrich_context()` 阻塞路由
- **位置**: `unified.py:1142`
- **问题**: 每次路由可能调用 `ProjectAnalyzer.analyze()` (~2s)
- **理想**: 异步或缓存

### P3.4 Matcher 预热竞争条件
- **问题**: `_warm_up_matchers()` 在 `finally` 中设置标志，无锁保护
- **风险**: 并发调用时双重预热

---

## 🔵 P4 — 文档/体验不一致

### P4.1 10 层 pipeline 对于长查询是"伪多层"
- **现象**: 查询 >5 字符时跳过 keyword/TF-IDF/embedding/levenshtein，直接 AI Triage
- **文档宣称**: "10 层 pipeline，逐层理解"
- **实际**: 长查询只有 2-3 层真正参与

### P4.2 `SkillRoute.to_dict()` 遗漏 `description`
- **位置**: `models.py`
- **问题**: 字段存在但序列化时静默丢弃

---

## 📊 影响矩阵

| 问题 | 用户影响 | 开发影响 | 修复成本 | 优先级 |
|------|---------|---------|---------|--------|
| P0.1 orchestrate 零测试 | 🔴 高 | 🔴 高 | 🟡 中 | **P0** |
| P0.2 route 废弃但未迁移 | 🟡 中 | 🟠 中 | 🟡 中 | **P0** |
| P0.3 测试超时 | 🟠 中 | 🔴 高 | 🟡 中 | **P0** |
| P0.4 LLM 工厂失败 | 🟡 中 | 🟠 中 | 🟢 低 | **P0** |
| P1.1 God Class | 🟢 低 | 🔴 高 | 🔴 高 | **P1** |
| P1.2 循环依赖 | 🟢 低 | 🟠 中 | 🟡 中 | **P1** |
| P2.1 裸 except | 🟠 中 | 🟠 中 | 🟢 低 | **P2** |
| P2.2 print() 泄漏 | 🟡 中 | 🟢 低 | 🟢 低 | **P2** |
| P3.1 重复 candidates | 🟡 中 | 🟢 低 | 🟢 低 | **P3** |
