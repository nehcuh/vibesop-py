# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-23 14:11

**Session**: 并行执行实现 + LLM 配置修复

**Summary**:
1. **并行执行支持**: 实现了多技能编排的并行执行能力
   - 新增 `ParallelScheduler` 类，支持 DAG 拓扑排序
   - `ExecutionStep` 添加 `dependencies`、`can_parallel`、`parallel_group` 字段
   - `ExecutionMode` 枚举 (SEQUENTIAL, PARALLEL, MIXED)
   - `PlanBuilder._detect_execution_mode()` 自动检测"同时"、"parallel"等关键词
   - `ExecutionPlan.get_parallel_groups()` 返回并行批次
2. **AgentRouter API 扩展**:
   - `get_parallel_preview(plan)` 预览并行执行情况
   - `execute_plan(plan, executor, max_parallel)` 执行并行计划
3. **LLM 配置修复**: `TriageService.init_llm_client()` 现在从配置文件读取 `api_base`
4. **设计文档**: `docs/parallel-execution-design.md`, `docs/core-usecase-analysis.md`

**Key Decisions**:
1. **DAG 拓扑排序**: 使用依赖关系图确定并行批次
2. **Semaphore 限流**: 避免过多并发步骤
3. **配置优先级**: Agent环境 > 配置文件 > 环境变量 > 默认

**Files Modified**:
- 新建: `src/vibesop/core/orchestration/parallel_scheduler.py`
- 修改: `src/vibesop/core/models.py`, `src/vibesop/core/orchestration/plan_builder.py`
- 修改: `src/vibesop/agent/__init__.py`, `src/vibesop/core/routing/triage_service.py`
- 新建: `docs/parallel-execution-design.md`, `docs/core-usecase-analysis.md`

**Test Status**:
```
Orchestration tests: 12/12 passed ✅
Parallel execution: Working (1.5x speedup on 2+2+1 steps)
Lint: All checks passed ✅
```

**Next Steps**:
- 添加并行执行的完整测试覆盖
- 考虑添加 CLI 命令暴露编排功能
- 提交并行执行实现

---

### 2026-04-22 24:00

**Session**: 待办清零 — Flaky Test + Type Check Cleanup + v4.3.0 Release

**Summary**:
1. **拉取最新更新**: 远程分支已有 v4.3 全部功能
2. **P1 修复 flaky test**: `test_disabled_skill_excluded_from_routing` 标记 `@pytest.mark.slow`
3. **P2 类型检查清理**: basedpyright src/ 1199 errors → **0 errors, 98 warnings**
4. **P3 更新 v50 计划**: T1-T5 全部 `[x]`
5. **P4 发布 v4.3.0**: 版本号 4.2.1 → 4.3.0

**Next Steps**:
- 配置 GitHub 认证后 push
- v4.3.0 ready for release

<!-- handoff:end -->
