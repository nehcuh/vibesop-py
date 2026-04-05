# VibeSOP v3.0 全面重构设计

> **Status**: Approved
> **Date**: 2026-04-05
> **Target**: v3.0.0 (breaking changes allowed)

## 1. 背景与动机

VibeSOP-Py 当前版本 2.1.0，综合评分 5.8/10。存在以下核心问题：

### 1.1 致命问题 (P0)

| 问题 | 位置 | 影响 |
|------|------|------|
| 双重模型系统 | `workflow/cascade.py` vs `workflow/models.py` | 维护负担、性能损耗、数据不一致风险 |
| Closure Bug | `workflow/pipeline.py:168` | 所有 handler 引用最后一个 stage，行为错误 |
| eval() 安全漏洞 | `builder/dynamic_renderer.py` | 代码执行风险 |
| MagicMock 生产代码 | `triggers/activator.py` | 测试工具泄漏到生产代码 |
| Pydantic v1 废弃 API | `workflow/models.py`, `workflow/state.py` | 未来版本兼容风险 |
| 硬编码开发者路径 | `scripts/sync-registry.py` | 其他贡献者无法使用 |

### 1.2 架构问题 (P0)

| 问题 | 位置 | 影响 |
|------|------|------|
| God Class | `engine.py` 280 行包含 5 层路由逻辑 | 难以测试、难以扩展 |
| 代码重复 | `detector.py` 语义精炼逻辑重复 | 维护困难 |
| CLI 命令堆积 | `main.py` 358 行 30+ 命令 | 难以发现、难以测试 |
| 未实现功能 | `resume_workflow()` NotImplementedError | API 承诺未兑现 |
| 同步 LLM 调用 | `llm/` 模块 | 阻塞事件循环 |

### 1.3 工程问题 (P1-P2)

| 问题 | 影响 |
|------|------|
| 覆盖率数据完全不可信 (stale coverage.xml) | 无法评估真实质量 |
| 零覆盖模块 6+ 个 | 重构无保护网 |
| 类型检查器不统一 (pyright vs basedpyright) | 类型安全承诺落空 |
| `Any` 类型滥用 (semantic 模块) | 类型检查形同虚设 |
| 无密钥扫描 | 密钥泄漏风险 |
| 无发布门禁 | 可能发布坏版本 |
| 运行时状态污染 repo | `.vibe/preferences.json` 等被跟踪 |
| 文档断裂引用 | 用户体验差 |

## 2. 设计原则

1. **破坏性允许** — 为 v3.0 准备，不保留向后兼容
2. **按模块逐个重构** — 修完一个模块跑一次测试，风险低，可回滚
3. **统一为 Pydantic models.py** — 保留运行时验证能力
4. **类型检查器统一为 basedpyright** — strict mode
5. **测试先行** — 重构前确保有测试保护网

## 3. 架构设计

### 3.1 模型统一方案

**决策**：统一为 Pydantic `models.py`，删除 `cascade.py` 中的重复定义。

```
Before:
  workflow/cascade.py  → WorkflowStep, StepStatus, ExecutionStrategy (dataclass/enum)
  workflow/models.py   → PipelineStage, StageStatus, ExecutionStrategy (Pydantic)

After:
  workflow/models.py   → 唯一定义 (Pydantic)
  workflow/cascade.py  → 引用 models.py，删除重复定义
  workflow/pipeline.py → 删除 _to_cascade_config() 转换层
```

### 3.2 路由引擎拆分

```
Before:
  core/routing/engine.py → SkillRouter (280 行，包含 5 层逻辑)

After:
  core/routing/engine.py     → SkillRouter (50 行，只负责编排)
  core/routing/handlers.py   → RoutingHandler ABC + 5 层实现
    ├── AITriageHandler (Layer 0)
    ├── ExplicitHandler (Layer 1)
    ├── ScenarioHandler (Layer 2)
    ├── SemanticHandler (Layer 3)
    └── FuzzyHandler (Layer 4)
```

### 3.3 语义精炼提取

```
Before:
  triggers/detector.py → KeywordDetector (446 行，包含语义精炼逻辑)

After:
  triggers/detector.py       → KeywordDetector (~200 行，只负责检测编排)
  triggers/semantic_refiner.py → SemanticRefiner (提取的公共语义逻辑)
```

### 3.4 CLI 命令分组

```
Before:
  cli/main.py → 358 行，30+ 命令直接注册

After:
  cli/main.py       → ~100 行，只保留核心命令 (route, doctor, version)
  cli/subcommands/  → 自动注册机制
  cli/commands/     → 各命令独立文件 (已存在，只需改进注册)
```

### 3.5 类型安全提升

| 模块 | 当前问题 | 修复方案 |
|------|---------|---------|
| semantic/models.py | `vector: Any \| None` | `vector: NDArray[np.float64] \| None` |
| semantic/encoder.py | 返回 `Any` | 返回 `NDArray[np.float64]` |
| integrations/models.py | `IntegrationInfo` 是普通类 | 改为 Pydantic BaseModel |
| 全局 | pyright 抑制注释过多 | 逐一审查，能修的修，不能修的加注释说明原因 |

## 4. 执行计划

### Phase 1: 致命 Bug 修复

| # | 任务 | 文件 | 验证 |
|---|------|------|------|
| 1.1 | 双重模型系统统一 | `workflow/cascade.py`, `workflow/models.py`, `workflow/pipeline.py` | 工作流测试通过 |
| 1.2 | Closure Bug 修复 | `workflow/pipeline.py:168` | 多 stage 工作流正确执行 |
| 1.3 | eval() 安全修复 | `builder/dynamic_renderer.py` | 条件评估测试通过 |
| 1.4 | MagicMock 清理 | `triggers/activator.py` | 导入无错误 |
| 1.5 | Pydantic v1 API 迁移 | `workflow/models.py`, `workflow/state.py` | 无 deprecation warning |
| 1.6 | 硬编码路径修复 | `scripts/sync-registry.py` | 脚本可配置运行 |

### Phase 2: 架构重构

| # | 任务 | 文件 | 验证 |
|---|------|------|------|
| 2.1 | 路由引擎拆分 | `core/routing/engine.py`, `core/routing/handlers.py` (新建) | 路由行为不变 |
| 2.2 | 语义精炼提取 | `triggers/detector.py`, `triggers/semantic_refiner.py` (新建) | 触发器测试通过 |
| 2.3 | CLI 命令分组 | `cli/main.py`, `cli/subcommands/` (新建) | 所有命令可用 |
| 2.4 | 未实现功能处理 | `workflow/manager.py` | API 一致 |
| 2.5 | LLM 异步支持 | `llm/base.py`, `llm/anthropic.py`, `llm/openai.py` | 异步调用正常 |

### Phase 3: 类型安全提升

| # | 任务 | 文件 | 验证 |
|---|------|------|------|
| 3.1 | 统一类型检查器 | `pyproject.toml`, `.pre-commit-config.yaml`, CI | basedpyright 0 errors |
| 3.2 | semantic Any 清理 | `semantic/models.py`, `semantic/encoder.py`, `semantic/cache.py` | 类型检查通过 |
| 3.3 | IntegrationInfo Pydantic 化 | `integrations/models.py` | 序列化/反序列化正常 |
| 3.4 | pyright 抑制注释审查 | 全局 | 每个 ignore 有注释 |
| 3.5 | 依赖定义统一 | `pyproject.toml` | 无重复定义 |

### Phase 4: 测试覆盖重建

| # | 任务 | 文件 | 验证 |
|---|------|------|------|
| 4.1 | 删除 stale coverage 文件 | `coverage.json`, `coverage.xml` | 干净状态 |
| 4.2 | 重新生成准确覆盖率 | 运行 pytest --cov | 面对真实数据 |
| 4.3 | 零覆盖模块补测试 | adapters, builder, cli/commands, hooks, installer, workflow | 覆盖率 ≥ 80% |
| 4.4 | 测试配置统一 | `pyproject.toml`, CI | 阈值一致 80% |
| 4.5 | 性能基准纳入 CI | `.github/workflows/ci.yml` | benchmark 在 CI 中运行 |

### Phase 5: 安全与 CI/CD

| # | 任务 | 文件 | 验证 |
|---|------|------|------|
| 5.1 | 密钥扫描 | `.pre-commit-config.yaml` | gitleaks 通过 |
| 5.2 | 提交 uv.lock | `.gitignore`, `uv.lock` | 可复现构建 |
| 5.3 | 发布前 CI 门禁 | `.github/workflows/release.yml` | 发布前跑 lint/test/type-check |
| 5.4 | Dependabot | `.github/dependabot.yml` | 自动 PR 依赖更新 |
| 5.5 | 清理 .github/ | `.github/*.md` 临时文档 | 只保留持久文档 |
| 5.6 | 运行时状态 .gitignore | `.gitignore` | preferences.json 等不跟踪 |

### Phase 6: 文档与工程规范

| # | 任务 | 文件 | 验证 |
|---|------|------|------|
| 6.1 | 清理临时文档 | `.github/V2.1.0-*.md` 等 | 只保留持久文档 |
| 6.2 | 统一 coverage 阈值 | `pyproject.toml`, CI | 都是 80% |
| 6.3 | Makefile security 目标 | `Makefile` | `make security` 可用 |
| 6.4 | 修复 README 断裂引用 | `README.md` | 所有链接有效 |
| 6.5 | 中文 README 同步 | `README.zh-CN.md` | 迁移状态准确 |
| 6.6 | REFACTORING.md 更新 | `REFACTORING.md` | 反映当前状态 |

## 5. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 双重模型系统重构可能破坏工作流 | 高 | 先写测试保护网，再重构 |
| 路由引擎拆分可能改变行为 | 高 | 保留现有路由测试作为回归检测 |
| LLM 异步可能影响现有同步调用方 | 中 | 保留同步 wrapper 作为过渡 |
| 类型修复可能暴露隐藏 bug | 中 | 每个修复独立提交，可回滚 |
| 测试覆盖提升工作量大 | 低 | 按模块逐个完成，不追求一次到位 |

## 6. 成功标准

- [ ] basedpyright strict mode 0 errors
- [ ] 测试覆盖率 ≥ 80% (真实数据)
- [ ] 所有现有测试通过 (无回归)
- [ ] CI 全绿 (lint + type-check + test + security)
- [ ] 无 eval()、MagicMock 生产代码、硬编码路径
- [ ] 无双重模型系统
- [ ] pre-commit 包含密钥扫描
- [ ] uv.lock 已提交
- [ ] 发布前 CI 门禁生效
- [ ] 文档无断裂引用

## 7. 文件变更预估

| 类型 | 数量 | 说明 |
|------|------|------|
| 新建文件 | ~15 | handlers.py, semantic_refiner.py, subcommands/, dependabot.yml, 测试文件等 |
| 修改文件 | ~30 | 所有 Phase 涉及的核心文件 |
| 删除文件 | ~10 | stale coverage, cascade.py 重复定义, 临时文档等 |
| 总变更行数 | ~5,000+ | 含新增测试 |
