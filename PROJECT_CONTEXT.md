# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-22 23:30

**Session**: v4.3 收尾 — Custom Matchers + A/B Testing Framework

**Summary**:
完成 v4.3 最后两项功能并推送到远程：
1. **Custom Matchers 插件系统**:
   - MatcherPluginRegistry 扫描 `.vibe/matchers/` 动态加载插件
   - Duck typing: 用户只需提供 `match(query, candidate) -> float` 函数
   - CLI: `vibe matcher list/register/remove/reload`
2. **A/B Testing Framework**:
   - Experiment/VariantConfig/RouteMetrics 模型
   - ExperimentRunner 对相同查询集运行不同变体
   - ExperimentAnalyzer 复合评分自动选择优胜者
   - CLI: `vibe experiment create/run/analyze/list/delete`
3. 新增 `RoutingLayer.CUSTOM` 和 `MatcherType.CUSTOM`
4. UnifiedRouter 自动加载 `.vibe/matchers/` 中的插件

**Key Decisions**:
1. **Duck typing for custom matchers**: 不强制 Protocol，函数即插件
2. **Config override for variants**: 实验变体是基线配置的增量覆盖
3. **JSON per experiment**: 人类可读、git friendly、零依赖

**Files Modified**:
- 新建: `src/vibesop/core/matching/plugin.py`, `src/vibesop/core/experiment.py`
- 新建: `src/vibesop/cli/commands/matcher_cmd.py`, `experiment_cmd.py`
- 修改: `src/vibesop/core/models.py`, `src/vibesop/core/matching/base.py`, `src/vibesop/core/routing/unified.py`
- 新建测试: `tests/core/test_matcher_plugin.py` (16), `test_experiment.py` (16)
- 推送: bf82aa5 -> origin/feature/routing-transparency

**Next Steps**:
- v4.3 全部完成，可考虑发布 v4.3.0
- 修复 flaky test 并行隔离问题
- 类型检查清理

**Test Status**:
```
1783 passed, 0 failed ✅
Lint: 0 errors ✅
```

---

### 2026-04-22 22:00

**Session**: 全面优化 + v4.3 功能开发（4 Phase 大规模迭代）

**Summary**:
执行了 4 个 Phase 的系统级开发：
1. Phase 1: 修复 133 个 lint 错误 → 0-error 基线
2. Phase 2: 完成 v50 最后缺口 — Badge/成就系统（4 种徽章）
3. Phase 3: UnifiedRouter God Class 重构 — 1210 行 → 506 行，提取 8 个 mixin
4. v4.3: Multi-Turn Support — 跟进查询检测（中英双语）、上下文增强路由
5. v4.3: Context-Aware Routing — 15+ 项目类型、13+ 技术栈检测

**Key Decisions**:
1. Badge 存储在 `~/.vibe/config.yaml`（user.badges），避免新增文件
2. Mixin 提取采用安全流程：每提取一个 mixin 都运行完整测试
3. ConversationContext 独立模块，不耦合 SessionContext
4. ProjectAnalyzer 采用文件存在性 + 内容关键字的双重检测策略

**Files Modified**:
- 新建: `src/vibesop/core/badges.py`, `conversation.py`, `project_analyzer.py`
- 新建: 8 个 routing mixin
- 修改: `src/vibesop/core/routing/unified.py` - 1210→506 行
- 修改: `src/vibesop/cli/main.py` - `--conversation` 参数
- 修改: 20+ 文件 lint 修复
- 新建测试: 64 个新测试

**Next Steps**:
- Custom Matchers 插件系统
- A/B Testing Framework
- 修复 flaky test 并行隔离问题

**Test Status**:
```
1751 passed, 1 flaky failed ✅
Lint: 0 errors ✅
Commit: 1733422 on main
```

<!-- handoff:end -->
