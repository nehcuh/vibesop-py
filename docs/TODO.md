# VibeSOP-Py 项目待办与进度记录

> **最后更新**: 2026-04-17  
> **版本**: v4.0.0  
> **状态**: 生产就绪优化中

---

## 📊 当前健康度（已更新）

| 维度 | 实际值 | 目标 | 状态 |
|------|--------|------|------|
| 测试通过 | 1308 passed, 1 skipped | — | ✅ |
| 测试覆盖率 | 82.30% | >55% | ✅ |
| Lint | 0 errors | 0 | ✅ |
| 类型检查 | 0 errors, 8 warnings | 0 errors | ✅ |
| 路由延迟 P95 | ~45ms | <50ms | ✅ |
| 路由吞吐 | >50 qps | >50 qps | ✅ |
| 路由准确率 | ~85% | >90% | ⚠️ |

---

## ✅ 近期已完成（2026-04-09 ~ 2026-04-17）

### Phase 1: 关键 Bug 修复
- [x] `TriageService` 正则匹配修复（不再错误匹配 `json` fence 关键字）
- [x] `OptimizationService` 移除 dead branch
- [x] `NamespacePriorityStrategy` 默认优先级修正（未知包降至 50）
- [x] OpenAI/Anthropic 异常处理改为透传原始异常类型
- [x] 移除冗余的 `ExplicitOverrideStrategy`

### Phase 2: 架构一致性
- [x] 场景配置统一为 `core/registry.yaml` 单一事实来源
- [x] 修复 `UnifiedRouter` 重复搜索路径导致的性能退化（恢复 >50 qps）
- [x] `ColdStartStrategy` 接入 `UnifiedRouter`（P0 技能优先级生效）
- [x] 清理冗余的 `pyright` suppression headers

### Phase 3: 测试与覆盖率
- [x] 新增 `tests/installer/test_skill_installer.py`（15 测试）
- [x] 扩展 `tests/installer/test_quickstart.py`（+17 测试）
- [x] 扩展 `tests/installer/test_transactional.py`（+11 测试）
- [x] 新增 `tests/core/routing/test_matcher_pipeline.py`（10 测试）
- [x] 新增冲突解决测试 `test_conflict_resolution.py`

### Phase 4: 类型检查与文档
- [x] 修复 basedpyright 0 errors
- [x] 更新 `PRODUCTION_READINESS_REVIEW.md` 至 8.5/10
- [x] 新增故障排查手册 `docs/user/troubleshooting.md`
- [x] 添加性能基准 CI（`.github/workflows/ci.yml` benchmark job）
- [x] 修复文档中过时的 layer 编号、版本号和成功指标

---

## ❌ 未完成 / 进行中

### P1 - 应该修复

| 项目 | 状态 | 说明 |
|------|------|------|
| 路由准确率优化 | ~85% | 目标 >90%；需优化 TF-IDF 权重或补充 scenario 映射 |
| 高复杂度模块拆分 | 待开始 | `unified.py:route()` 248 行，`analyze.py` 432 行 |
| API 参考文档 | 待开始 | 缺少 `UnifiedRouter`、`MatcherPipeline` 等公共 API 文档 |

### P2 - 可选优化

| 项目 | 状态 | 说明 |
|------|------|------|
| pre-commit hooks | 未开始 | 自动 ruff + basedpyright |
| 国际化支持 | 未开始 | CLI 消息多语言 |
| 遥测数据收集 | 未开始 | 可选使用统计 |

---

## 🗂️ 关键文件索引

```
统一模型:      src/vibesop/core/models.py (RoutingLayer, SkillRoute, RoutingResult)
核心路由:      src/vibesop/core/routing/unified.py (UnifiedRouter)
配置管理:      src/vibesop/core/config/manager.py (ConfigManager)
优化引擎:      src/vibesop/core/optimization/
安全模块:      src/vibesop/security/
CLI 入口:      src/vibesop/cli/main.py
注册表:        core/registry.yaml (44 skills)
```

---

## 🚦 下一步建议

1. **如果要 Ship v4.0.0**: 完成 API 参考文档 + 运行完整测试 → 创建 Release PR
2. **如果要继续优化**: 优先提升路由准确率（TF-IDF 权重调优）
3. **如果要重构**: 拆分 `unified.py` 和 `analyze.py` 中的大函数

---

*注：历史 Phase 1-7 详细记录已归档至 `docs/superpowers/plans/`。*
