# VibeSOP 下一步优化工作计划

> **计划版本**: 1.0.0
> **创建日期**: 2026-04-28
> **基于评审**: 深度项目分析报告
> **策略**: 先止血 (P0) → 再重构 (P1) → 后打磨 (P2/P3)

---

## 总体策略

```
Phase 1: 止血与基础修复 (1-2 天)
    └── 修复测试失败、测试超时、LLM工厂问题
    
Phase 2: 测试覆盖攻坚 (3-5 天)
    └── orchestrate() 测试、CLI 测试、核心路由测试
    
Phase 3: 架构重构准备 (2-3 天)
    └── God Class 分解设计、循环依赖清理
    
Phase 4: 代码质量治理 (2-3 天)
    └── 裸 except、print调试、类型安全、重复代码
    
Phase 5: 性能优化 (1-2 天)
    └── Router 复用、重复计算消除、竞争条件修复
    
Phase 6: 验证与收尾 (1 天)
    └── 全量测试通过、覆盖率验证、文档更新
```

**总预计工期**: 10-16 天（可并行部分任务）

---

## Phase 1: 止血与基础修复 🩹

**目标**: 让测试套件可运行、无失败
**工期**: 1-2 天
**验收标准**: `pytest` 5 分钟内完成，0 失败

### 1.1 修复 LLM 工厂测试失败
- **文件**: `tests/llm/test_llm_factory.py`
- **任务**: 分析 provider 验证逻辑变更，同步测试断言
- **预计**: 2-4 小时
- **验收**: `pytest tests/llm/test_llm_factory.py -x` 全绿

### 1.2 诊断并修复测试超时
- **任务**:
  1. 使用 `pytest --durations=10` 找出最慢的测试
  2. 检查是否有测试在真实调用 LLM API（应 mock）
  3. 检查 fixtures 是否在每次测试重复做文件 I/O
  4. 检查是否有测试在 `setUp` 中初始化 Embedding 模型
- **预计**: 4-6 小时
- **验收**: `pytest --co -q | wc -l` 收集的测试在 300s 内全部完成

### 1.3 修复 `get_parallel_groups()` 浪费计算
- **文件**: `src/vibesop/core/models.py:408`
- **任务**: 移除未使用的 dict comprehension
- **预计**: 15 分钟
- **验收**: 代码审查通过

---

## Phase 2: 测试覆盖攻坚 🧪

**目标**: 核心功能有测试守护
**工期**: 3-5 天
**验收标准**: 核心模块覆盖率 >60%，CLI 覆盖率 >30%

### 2.1 `orchestrate()` 测试套件
- **文件**: 新建 `tests/core/routing/test_orchestration.py`
- **测试场景**:
  - [ ] 单意图查询 → 退化到单技能路由
  - [ ] 多意图查询 → 正确分解为子任务
  - [ ] 编排禁用配置 → 直接单技能路由
  - [ ] 分解失败 → 优雅降级到单技能
  - [ ] 回调机制 → 各阶段回调被正确调用
  - [ ] 流式进度 → 实时状态更新
- **预计**: 1-2 天
- **验收**: `pytest tests/core/routing/test_orchestration.py` 全绿

### 2.2 `route()` → `orchestrate()` 内部迁移
- **文件**:
  - `src/vibesop/core/skills/slash_commands.py:313`
  - `src/vibesop/agent/__init__.py:552`
  - 所有内部调用点
- **任务**:
  1. 识别所有内部 `route()` 调用
  2. 评估每个调用点是否应使用 `orchestrate()`
  3. 为保持子路由性能的场景，保留 `route()` 但消除 DeprecationWarning
  4. 更新 docstring 和错误消息
- **预计**: 4-6 小时
- **验收**: `grep -r "\.route(" src/ --include="*.py" | wc -l` 减少至合理的内部使用点

### 2.3 CLI 核心命令测试
- **文件**: 新建/补充 `tests/cli/test_route_cmd.py`, `test_orchestrate_cmd.py`
- **测试场景**:
  - [ ] `vibe route "query"` — 正常路由
  - [ ] `vibe route --json` — JSON 输出格式正确
  - [ ] `vibe route --explain` — 透明度报告正确
  - [ ] `vibe orchestrate "query"` — 编排模式
  - [ ] `vibe decompose "query"` — 分解模式
  - [ ] `--yes` / `-y` 标志 — 跳过确认
- **预计**: 1-2 天
- **验收**: CLI 路由相关命令有基本覆盖

### 2.4 核心路由逻辑测试增强
- **文件**: `tests/core/routing/`
- **任务**:
  - [ ] `_route()` 各分支覆盖（显式、场景、AI Triage、Matcher、Fallback）
  - [ ] `_build_match_result()` 覆盖
  - [ ] `_enrich_context()` 覆盖
  - [ ] 降级逻辑覆盖（4 级降级）
- **预计**: 1-2 天
- **验收**: `unified.py` 覆盖率从 14% → >40%

---

## Phase 3: 架构重构准备 🏗️

**目标**: 为 God Class 分解做好设计和准备
**工期**: 2-3 天
**验收标准**: 有明确的重构设计文档，循环依赖数量减少

### 3.1 `UnifiedRouter` 分解设计
- **任务**:
  1. 设计 `LayerStrategy` 接口：
     ```python
     class LayerStrategy(Protocol):
         def match(self, query, candidates, context) -> MatchResult | None: ...
         @property
         def priority(self) -> int: ...
     ```
  2. 将 10 层路由提取为独立策略类
  3. 设计 `RoutingPipeline` 组合器
  4. 编写 ADR 文档记录重构决策
- **文件**: 新建 `docs/architecture/adr-router-refactor.md`
- **预计**: 1-2 天
- **验收**: ADR 通过评审，接口设计获得认可

### 3.2 循环依赖清理
- **任务**:
  1. 使用 `python -c "import vibesop"` 配合工具分析导入图
  2. 识别循环依赖环
  3. 通过以下方式打破循环：
     - 提取共享接口到 `types.py` 或 `protocols.py`
     - 使用 `TYPE_CHECKING` 导入
     - 延迟导入改为依赖注入
  4. 优先清理 `unified.py` 中的方法内导入
- **预计**: 1 天
- **验收**: `unified.py` 中方法内 import 减少 80%+

### 3.3 Mixin 接口化
- **文件**: `orchestration_mixin.py`, `execution_mixin.py`, `stats_mixin.py`
- **任务**:
  1. 为每个 Mixin 定义 Protocol，声明所需属性
  2. 移除 `getattr(self, "_xxx", None)` 模式
  3. 移除 `# type: ignore[attr-defined]`
- **预计**: 4-6 小时
- **验收**: Mixin 文件 0 个 `# type: ignore`

---

## Phase 4: 代码质量治理 🧹

**目标**: 消除明显的代码臭味
**工期**: 2-3 天
**验收标准**: 裸 except 减少 80%，生产代码 0 个 print()

### 4.1 裸 `except Exception` 治理
- **策略**:
  1. 逐个文件审查，将 `except Exception` 改为具体异常
  2. 如果确实需要捕获所有异常，必须记录 traceback：
     ```python
     except Exception as e:
         logger.exception("...")
         raise  # 或返回错误结果
     ```
  3. 高风险文件优先：`candidate_manager.py`, `orchestration_mixin.py`, `retention.py`
- **预计**: 1 天
- **验收**: `grep -r "except Exception" src/ --include="*.py" | wc -l` < 6

### 4.2 移除生产代码中的 `print()`
- **文件**: `llm/openai.py`, `llm/anthropic.py`, `llm/ollama.py`, `core/ai_enhancer.py`, ...
- **策略**:
  1. LLM 模块的 `print(response.content)` → 改为 `logger.debug()`
  2. builder 模块的进度打印 → 改为通过回调接口报告
  3. 如果是 docstring 示例代码，确认不会被意外执行
- **预计**: 2-4 小时
- **验收**: `grep -r "print(" src/ --include="*.py" | grep -v "logger" | wc -l` → 仅保留合理的调试/示例代码

### 4.3 统一深合并实现
- **任务**:
  1. 将 `utils/helpers.py:merge_dicts()` 增强为支持递归
  2. 替换 `core/config/manager.py` 和 `builder/overlay.py` 中的重复实现
  3. 为合并函数编写单元测试
- **预计**: 2-3 小时
- **验收**: 只有一个深合并实现，有测试

### 4.4 类型安全修复
- **任务**:
  1. 移除 `unified.py` 顶部的全局 `# pyright: ignore`
  2. 逐个修复类型错误，或添加有针对性的 `# type: ignore[xxx]` 并附注释说明原因
  3. 修复 `project_analyzer.py:114` 的 `None→list[str]` 赋值
  4. 修复 `orchestration/callbacks.py:44` 的类似问题
- **预计**: 4-6 小时
- **验收**: 全局类型忽略移除，具体忽略附带解释

### 4.5 死代码清理
- **任务**:
  1. 移除 `cli/main.py:730-735` 的不可达代码
  2. 移除 `llm_config.py:417` 的无用赋值
  3. 运行 `vulture` 或类似工具检测未使用代码
- **预计**: 1-2 小时
- **验收**: 无明显的死代码

---

## Phase 5: 性能优化 ⚡

**目标**: 消除明显的性能浪费
**工期**: 1-2 天
**验收标准**: 基准测试显示改善

### 5.1 Router 实例复用
- **任务**:
  1. 在 CLI 层面引入 `RouterCache` 或单例模式
  2. 跨 CLI 命令复用已初始化的 `UnifiedRouter`
  3. 注意：需要处理不同 project_root 的情况
  4. 备选方案：进程级缓存（`@lru_cache` + 进程池）
- **文件**: `cli/main.py`
- **预计**: 4-6 小时
- **验收**: 连续 CLI 命令的启动时间显著降低

### 5.2 消除重复计算
- **任务**:
  1. `_build_match_result()` 中 candidates 只获取一次
  2. `get_parallel_groups()` 移除未使用的 dict comprehension
  3. 检查其他方法中的重复 I/O
- **预计**: 2-3 小时
- **验收**: 代码审查通过

### 5.3 `_enrich_context()` 优化
- **任务**:
  1. `ProjectAnalyzer.analyze()` 结果持久化到 `.vibe/project_analysis.json`
  2. 只在项目结构变化时重新分析（基于文件 mtime）
  3. 或改为异步/后台线程执行
- **预计**: 2-4 小时
- **验收**: 首次路由后，后续路由不再阻塞于 project analysis

### 5.4 Matcher 预热线程安全
- **任务**:
  1. 在 `_warm_up_matchers()` 中使用 `_stats_lock` 保护标志设置
  2. 或使用 `threading.Event` 替代布尔标志
- **预计**: 1 小时
- **验收**: 并发路由测试通过

---

## Phase 6: 验证与收尾 ✅

**目标**: 确保优化不引入回归
**工期**: 1 天
**验收标准**: 全量测试通过，覆盖率提升可量化

### 6.1 全量测试验证
- **任务**: `pytest` 全量运行，确认：
  - [ ] 0 失败
  - [ ] 5 分钟内完成
  - [ ] 无新增 warning
- **预计**: 2-4 小时（含调试）

### 6.2 覆盖率验证
- **任务**:
  - [ ] 生成覆盖率报告
  - [ ] 核心模块 (`core/routing/`, `cli/`) 覆盖提升对比
  - [ ] 记录覆盖率基线
- **预计**: 1 小时

### 6.3 文档更新
- **任务**:
  - [ ] 更新 `PROJECT_STATUS.md` — 标记已修复的问题
  - [ ] 更新 `ROADMAP.md` — 记录技术债清理进展
  - [ ] 如有架构变更，更新 `ARCHITECTURE.md`
- **预计**: 2 小时

### 6.4 回归测试
- **任务**:
  - [ ] 手动测试核心 CLI 命令：`vibe route`, `vibe orchestrate`, `vibe skills list`
  - [ ] 验证 JSON 输出仍然正确
  - [ ] 验证中文查询路由正常
- **预计**: 1-2 小时

---

## 并行化建议

以下任务可以并行进行：

```
Week 1
├── Day 1-2: Phase 1 (测试修复) + Phase 4.2 (print清理) + Phase 4.5 (死代码)
├── Day 3-4: Phase 2 (测试攻坚) + Phase 4.1 (except治理)
└── Day 5: Phase 3.1 (Router分解设计) + Phase 5.2 (重复计算)

Week 2
├── Day 1-2: Phase 3 (架构重构准备) + Phase 5 (性能优化)
├── Day 3: Phase 4.3 (深合并统一) + Phase 4.4 (类型安全)
└── Day 4-5: Phase 6 (验证收尾)
```

---

## 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 重构引入回归 | 中 | 高 | 每个重构必须有测试守护，小步提交 |
| 测试迁移工作量超预期 | 高 | 中 | 优先覆盖 happy path，边缘 case 后续补充 |
| God Class 分解影响接口稳定性 | 中 | 高 | 保持公共 API 不变，只重构内部实现 |
| 循环依赖清理引发连锁修改 | 中 | 中 | 每次只清理一个环，充分测试后再下一步 |

---

## 完成定义 (Definition of Done)

- [ ] `pytest` 在 5 分钟内完成，0 失败
- [ ] `unified.py` 覆盖率 ≥ 40%
- [ ] `cli/main.py` 覆盖率 ≥ 30%
- [ ] 生产代码 0 个裸 `print()`
- [ ] 裸 `except Exception` ≤ 5 处（且都有日志记录）
- [ ] `unified.py` 中方法内 import 减少 80%
- [ ] Router 分解 ADR 完成
- [ ] 手动回归测试通过
