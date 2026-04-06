# VibeSOP-Py 项目待办与进度记录

> **最后更新**: 2026-04-06
> **分支**: `feature/external-skill-integration`
> **总提交**: 24+
> **测试**: 1460 passed, 42 skipped, 62.62% coverage

---

## ✅ 已完成 (5 个 Phase)

### Phase 1: 地基 — 三层优化引擎 + 状态管理
- [x] OptimizationConfig 模型 (PrefilterConfig, PreferenceBoostConfig, ClusteringConfig)
- [x] 统一状态管理 (StateManager, schema, migration)
- [x] Layer 1: 候选预过滤 (Priority → Namespace → Cluster)
- [x] Layer 2: 偏好学习接入 (70/30 权重混合)
- [x] Layer 3: 语义聚类 (TF-IDF + KMeans, 自动冲突解决)
- [x] UnifiedRouter 集成三层优化管道
- [x] omx 命名空间 + 5 条冲突解决规则
- **测试**: 55 个新增

### Phase 2: 核心 omx/ 技能 (deep-interview + ralph + ralplan)
- [x] deep-interview: 模糊度评分引擎 + 压力梯 + 结晶器
- [x] deep-interview SKILL.md
- [x] ralph: 持久化循环 + Deslop 引擎 + 分层验证
- [x] ralph SKILL.md
- [x] ralplan: RALPLAN-DR 审议 + Architect + Critic + Gate
- [x] ralplan SKILL.md
- [x] Registry 添加 3 个 omx/ 技能条目
- **测试**: 21 个新增

### Phase 3: 流水线 omx/ 技能 (team + ultrawork + autopilot + ultraqa)
- [x] team: 文件邮箱 + Worker 协议 + 监控报告
- [x] team SKILL.md
- [x] ultrawork: 三级任务分配 (LOW/STANDARD/THOROUGH)
- [x] ultrawork SKILL.md
- [x] autopilot: 6 阶段流水线 (clarify→plan→gate→execute→verify→ship)
- [x] autopilot SKILL.md
- [x] ultraqa: Bug 生命周期 + 自动停止条件
- [x] ultraqa SKILL.md
- [x] Registry 添加 4 个 pipeline 技能条目
- **测试**: 31 个新增

### Phase 4: 集成测试
- [x] 端到端路由测试 (44 技能)
- [x] 预过滤有效性测试 (70%+ 候选减少)
- [x] 性能基准 (P95 < 50ms)
- **测试**: 19 个新增

### Phase 5A: CLI 执行缺口修复
- [x] `vibe execute <skill_id> <query>` 命令
- [x] `vibe route <query> --run` 模式
- [x] `vibe execute list` 列出可用技能
- [x] 更新 `vibe auto` deprecation 信息
- **测试**: 4 个新增

### Phase 5B: omx/ CLI 集成
- [x] 7 个快捷命令 (interview/ralph/plan/team/ultrawork/autopilot/ultraqa)
- [x] `vibe omx list` 列出所有方法论
- **测试**: 8 个新增

### Phase 5C: 缺失路由层补全
- [x] Layer 1: Explicit Override (`!skill_id` / use/run/execute 动词)
- [x] Layer 2: Scenario Pattern (registry.yaml 11 条策略)
- [x] AI Triage Layer (Layer 0): LLM 语义分类 + 缓存 + 优雅降级
- **测试**: 21 个新增

---

## ❌ 未完成 (重要)

### 高优先级

| 项目 | 状态 | 说明 |
|------|------|------|
| **rtk 集成** | 0% | 仅检测条目，Token 优化、hooks 集成、代理层未实现 |
| **karpathy/autoresearch evaluator** | 30% | `_run_evaluator()` 返回硬编码 `5.0`，需实现真实评估逻辑 |
| **Workflow 执行器** | 30% | `CascadeExecutor.run_workflow()` 返回 `success=True` 但不执行 |
| **双模型统一** | 部分 | `core/models.py` (Pydantic) vs `core/routing/unified.py` (dataclass) 两套并存 |
| **废弃模块清理** | 未开始 | `triggers/` 和 `semantic/` 标记 deprecated 但未移除 |
| **ConfigLoader vs ConfigManager** | 部分 | 两套配置系统并存 |

### 中优先级

| 项目 | 状态 | 说明 |
|------|------|------|
| **AI Triage 生产就绪** | 基础完成 | 需要真实 LLM 调用集成测试、token 用量监控、成本上限配置 |
| **omx/ 技能实际执行逻辑** | SKILL.md 完成 | Python 实现是框架层，实际 LLM 调用/文件操作逻辑待补全 |
| **CLI 帮助文档** | 基础 | `vibe --help` 需要更新反映新命令 |
| **端到端集成测试** | 部分 | 缺少 omx/ 技能通过 CLI 的完整 E2E 测试 |

### 低优先级

| 项目 | 状态 | 说明 |
|------|------|------|
| **文档更新** | 部分 | README/CLAUDE.md 需要反映 v3.1.0 变更 |
| **性能基准 CI** | 未开始 | 路由性能回归检测自动化 |
| **技能市场** | 未开始 | 技能安装/同步/版本管理 |

---

## 📊 项目健康度

| 维度 | 评分 | 说明 |
|------|------|------|
| oh-my-codex 吸收 | **100%** | 7/7 方法论完整实现 (SKILL.md + Python) |
| superpowers/gstack | **80%** | 技能集成稳定 |
| karpathy/autoresearch | **30%** | 框架完整，evaluator 是 placeholder |
| rtk | **5%** | 仅检测条目 |
| 内部一致性 | **良好** | 统一模型、优化引擎接入，但双模型/废弃模块待清理 |
| 测试覆盖 | **62.62%** | 超过 55% 阈值 |
| 路由质量 | **优秀** | 8 层管道 + 3 层优化，44 技能无降级 |

---

## 🗂️ 关键文件索引

```
核心路由: src/vibesop/core/routing/unified.py
优化引擎: src/vibesop/core/optimization/
状态管理: src/vibesop/core/state/
omx 技能: src/vibesop/core/{interview,ralph,plan,team,pipeline}/
omx SKILL: core/skills/omx/{deep-interview,ralph,ralplan,team,ultrawork,autopilot,ultraqa}/
CLI: src/vibesop/cli/commands/{execute,omx}.py
配置: src/vibesop/core/config/{manager,optimization_config}.py
注册表: core/registry.yaml
测试: tests/test_*.py (13 个新测试文件)
```

---

## 🚦 下一步建议

1. **如果要 Ship**: 跑完整 lint + typecheck + 全量测试 → 创建 PR
2. **如果要继续开发**: 优先 rtk 集成 或 autoresearch evaluator 补全
3. **如果要清理**: 统一双模型 → 移除废弃模块 → 清理 ConfigLoader

---

*此文件由 vibesop-py 项目自动生成，供后续会话恢复上下文使用。*
