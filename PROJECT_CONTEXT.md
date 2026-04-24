# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-23 16:30

**Session**: Agent Runtime 层实现 + 平台适配 + E2E 验证

**Summary**:
1. **Agent Runtime 核心模块**（4 个模块，36 单元测试，全部通过）
   - `IntentInterceptor`: 意图拦截，支持短查询过滤、元查询检测、显式覆盖、多意图标记检测
   - `SkillInjector`: 平台特定注入（Claude Code additionalContext / OpenCode system_prompt / Kimi CLI instruction）
   - `DecisionPresenter`: 路由决策透明化（人类可读 + 结构化 JSON）
   - `PlanExecutor`: 多步骤执行指南（并行/串行、依赖跟踪、完成标记 `步骤 N 完成`）
2. **平台适配完成**:
   - Claude Code: `hooks/vibesop-route.sh` + `vibesop-track.sh` + `rules/routing.md` Agent Runtime Rules
   - Kimi CLI: `AGENTS.md` 强制路由规则 + 多意图处理 + 降级逻辑
   - OpenCode: plugin 参考模板（index.ts + README.md，待 API 稳定后接入）
3. **E2E 验证**: `tests/e2e/test_agent_runtime.py` 13 个测试全部通过
   - 完整链路: query → Interceptor → Injector → Presenter → Executor
   - 平台适配器文件生成验证
   - 跨平台一致性验证

**Key Decisions**:
1. Claude Code hook 脚本作为文档/参考生成（标准版不支持 UserPromptSubmit/PreToolUse）
2. OpenCode plugin 模板暂不接入 render_config()（API 标注 experimental）
3. E2E 采用 Python 层模拟（不依赖真实 AI Agent 平台），确保 CI 可运行

**Files Modified**:
- 新建: `src/vibesop/agent/runtime/`（4 核心模块）
- 新建: `tests/agent/runtime/`（36 单元测试）
- 新建: `tests/e2e/test_agent_runtime.py`（13 E2E 测试）
- 新建: `src/vibesop/adapters/templates/claude-code/hooks/`（2 hook 模板）
- 新建: `src/vibesop/adapters/templates/opencode/plugin/vibesop/`（2 plugin 文件）
- 修改: `src/vibesop/adapters/claude_code.py`, `src/vibesop/adapters/kimi_cli.py`
- 修改: `src/vibesop/adapters/templates/claude-code/rules/routing.md.j2`

**Test Status**:
```
139 passed, 0 failed ✅
  - agent/runtime: 36 passed
  - adapters: 90 passed
  - e2e/agent_runtime: 13 passed
```

**Next Steps**:
- Phase 3: 真实平台验证（Claude Code hook 实际触发、Kimi CLI AGENTS.md 遵守率）
- CLI: `vibe build --platform=all` 支持
- OpenCode plugin: 待 API 稳定后接入 render_config()

---

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

<!-- handoff:end -->
