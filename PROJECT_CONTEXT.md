# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-07-27 S37 [vibesop-py] Dashboard v3 Phase A — Tasks 1-9 (data instrumentation)

**Session Summary**:
- Task 1-5 (前序 session)：trace context 包裹 + workflow_node phase spans + per-step task_id binding (P0-1) + orchestration_id/trace_id 写 conversation metadata
- Task 6 / P0-3：mirror hook `--include-subagents`；`import_subagent` 双写 `parent_session`（raw, legacy）+ `parent_conversation_id`（resolved, 新 JOIN key）
- Task 7：`Reflection` dataclass — 7 kinds × 3 statuses × 5 target_types；dataclass + Literal + `__post_init__`（不引 Pydantic）；JSON round-trip 13/13
- Task 8：`ReflectionStore` append + `list_all` — JSONL append-only，cross-process lock（POSIX fcntl inline / Windows cross_process_lock）；4-thread × 25-write 无 interleaving
- Task 9：`list_by_task` / `list_open` / `update_status` — atomic rewrite via AtomicWriter（tmp+rename），同一把 cross-process lock 防 lost-update race；2-thread × 10-update 无 lost mutation

**Key Decisions**:
- PEP 567 contextvars 不跨进程 — sub-agent 跑独立 OS process，跨进程 JOIN 必须落盘
- JSONL store 双锁 pattern：in-process threading.Lock + cross-process fcntl/cross_process_lock；append + update 共用同一把 cross-process lock
- Plan path (`src/vibesop/observability/`) 与 codebase 约定 (`src/vibesop/core/observability/`) 冲突时跟约定，避免分裂
- update_status unknown id → KeyError（fail loud）；理由：stale id post-rebuild 是 dashboard bug，silent no-op 会掩盖

**Next Steps**:
- 11 commits 待 push
- Task 10 (P0-2 mandatory)：`Orchestrator.orchestrate()` 接 `PlanTracker.create_plan()` + `plan.metadata["trace_id"]` — DAG rebuilder plan↔span JOIN 契约
- Task 11/12：DAG rebuilder (load_plans_for_trace + build step tree)
- Task 13：fixture-based E2E (zero LLM)；验收关卡从 fill rate 改为 rebuild_dag smoke

### 2026-07-25 S36 [vibesop-py] Conversation mirror Path-2 — sub-agent transcripts

**Session Summary**:
- Path-2 实现：每个 sub-agent 独立 mirror conversation（agentType/description/parent_session 元数据）
- id 稳定性：`<parent>-sub-<sanitized_agent_id>` — meta 编辑/mtime 重排不 orphan
- 路径安全：`_sanitize_for_path` strip `[^A-Za-z0-9_-]+`（path-traversal 防御）
- Dashboard：type badge + 描述（escape；preview fallback 也 escape）；data-conv-id + addEventListener
- CLI flag：`--include-subagents/--no-include-subagents`（默认 on）
- grok+pi 评审 8 must-fix 全修，单独拆 test commit；grok 抓到 pi 漏的 XSS

**Key Decisions**:
- Sub-agent 存储路径：`<session-id>/subagents/agent-<hex>.jsonl` + sibling `.meta.json`
- macOS zsh `cp` 是 `cp -i` alias，shell pipeline 中用 `/bin/cp` 绕过
- `Path.iterdir` monkeypatch 安全，`Path.stat` monkeypatch 破坏 pytest tmp_path cleanup

**Next Steps**:
- 24 commits 待 push（d7ddfeb Path-1 / 6f2f7f0+23f478e Path-2 + 其他 instinct loop / diagnosis 提交）
- 等 instinct loop 24h 观察结果（2026-07-24 装 launchd，今天 review）

### 2026-07-21 S35 [vibesop-py] 文档审计 + CI 修复 + v8.0.0 发布

**Session Summary**:
- 审计并修复全部 87 个文档文件（版本号、架构、命令引用），归档 11 个历史文件
- Dashboard deps 移入 core，开箱即用
- 修复 3 个 Windows 测试（tick lock + encoding）
- 修复 CI lint（29 errors）和 release workflow（SHA 过期）
- v8.0.0 成功发布到 PyPI

**Key Decisions**:
- Action SHAs: 非安全关键用 version tag（@v2），安全关键可 pin SHA
- Windows 编码: 跨平台代码必须显式 `encoding="utf-8"`
- Dashboard: fastapi/uvicorn 入 core deps，默认安装

**Next Steps**:
- 全局工具重装: `uv tool install --reinstall /path/to/vibesop-py`
- 旧项目需手动创建 config.toml 启用 analytics
<!-- handoff:end -->
