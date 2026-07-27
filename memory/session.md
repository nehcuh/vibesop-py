
### S37 (2026-07-27) [vibesop-py] Dashboard v3 Phase A — Tasks 1-9 (data instrumentation)

- [x] **Task 1-5** (前序 session 已完成)：trace context 包裹 + workflow_node phase spans + per-step task_id binding (no plan_id fallback, P0-1) + orchestration_id/trace_id 写入 conversation metadata (Task 5 跨进程 JOIN)
- [x] **Task 6 / P0-3**：mirror hook 加 `--include-subagents`；`import_subagent` 新增 `parent_conversation_id` 写入 metadata（双写策略：legacy `parent_session`=raw + 新 `parent_conversation_id`=resolved mirror id）；CLI `conversation_cmd.py` 把 `cid` 透传进去
- [x] **Task 7**：`Reflection` dataclass — 7 kinds (routing_miss/skill_misuse/trigger_vague/cost_blow/agent_choice/positive_pattern/context_note) × 3 statuses (open/addressed/dismissed) × 5 target_types；dataclass + Literal + `__post_init__` 校验（不引 Pydantic）；JSON round-trip 13/13
- [x] **Task 8**：`ReflectionStore` append + `list_all` — JSONL append-only，cross-process lock（POSIX fcntl inline / Windows cross_process_lock）+ threading.Lock，pattern 直接抄 SpanWriter._locked_append；4-thread × 25-write 含 500-byte payload 无 interleaving
- [x] **Task 9**：`list_by_task` / `list_open` / `update_status` — atomic rewrite 用 AtomicWriter（tmp+rename），同一把 cross-process lock 防 lost-update race；unknown id raise KeyError（fail loud 不 silent no-op）；2-thread × 10-update 无 lost mutation

**Commits**：`a760971` (Task 6) / `aecccc7` (Task 7) / `faf762f` (Task 8) / `614e877` (Task 9) — 累计 11 commits ahead of origin/main

**Key Discoveries**:
1. **PEP 567 contextvars 不跨进程**：sub-agent 跑独立 OS process，`contextvars` 在 fork/spawn 后丢失 — 跨进程 JOIN 必须落盘（conversation metadata），不能靠 in-process var
2. **JSONL store 双锁 pattern**：in-process threading.Lock + cross-process fcntl/cross_process_lock 两层叠加；append 走 locked_append，update 走 atomic rewrite（AtomicWriter tmp+rename），两层用同一把 cross-process lock 防 appender vs updater race
3. **Plan path 与 codebase 约定冲突时跟约定**：plan 写 `src/vibesop/observability/reflection.py`（top-level），实际 codebase observability 全在 `src/vibesop/core/observability/`（与 tracer/aggregator/span_writer/models 同居）— 选了后者避免分裂
4. **Plain dataclass + Literal + `__post_init__` validator**：避免为单个 dataclass 引入 Pydantic 依赖；`__post_init__` 内做 `_validate_choice(value, frozenset(get_args(Literal)), field_name)` 即可达到 runtime 校验效果
5. **update_status fail loud 设计**：unknown id → KeyError（而非 silent no-op）；理由：stale id post-rebuild 是 dashboard bug，silent no-op 会掩盖

**Next Steps**:
- 11 commits 待 push（Task 1-9 + design docs + bind_task_context 早期 ship）
- Task 10 (P0-2 mandatory)：`Orchestrator.orchestrate()` 接 `PlanTracker.create_plan()` + `plan.metadata["trace_id"]` — DAG rebuilder 的 plan↔span JOIN 契约，目前完全没接
- Task 11/12：DAG rebuilder (load_plans_for_trace + build step tree)
- Task 13：fixture-based E2E (zero LLM) — 验收关卡从 fill rate 改为 rebuild_dag 真实数据 smoke

**Recorded**: yes — Phase A Tasks 1-9 progress + cross-process JSONL store pattern → auto-memory project-dashboard-v3-phase-a-tasks-1-9-shipped.md

### S36 (2026-07-25) [vibesop-py] Conversation mirror Path-2 — sub-agent transcripts

- [x] **Path-2 实现**：discover_subagents + import_subagent + derive_subagent_conversation_id；每个 sub-agent 独立 mirror conversation，metadata bag (agentType/description/parent_session/tool_use_id/agent_id/is_subagent)
- [x] **id 稳定性**：format `<parent>-sub-<sanitized_agent_id>`，不含 spawn index 也不含 agentType — meta 编辑/mtime 重排不 orphan
- [x] **路径安全**：`_sanitize_for_path` strip `[^A-Za-z0-9_-]+`；path-traversal 防御（`../../etc/passwd` 类 agentId 不能逃逸 storage_dir）
- [x] **Dashboard**：type badge + 描述（escapeHtml；preview fallback 也 escape — 修了非 sub-agent 的 XSS 隐患）；data-conv-id + addEventListener 替代 inline onclick
- [x] **CLI flag**：`--include-subagents/--no-include-subagents`（默认 on）；`--purge` 同时清主+子 conversation 文件
- [x] **grok+pi 评审**：8 must-fix 全修，单独拆为 `23f478e` test commit；grok 抓到 pi 漏的 XSS（c.preview fallback 未 escape）
- [x] **E2E 验证**：cmspark 4c0b62ec → 2711 主 turns + 1156 sub-agent turns across 24 sub-agents

**Commits**: `6f2f7f0` (feat) + `23f478e` (test) — 24 commits ahead of origin/main, unpushed

**Key Discoveries**:
1. Claude Code sub-agent 存储路径：`<session-id>/subagents/agent-<hex>.jsonl` + sibling `.meta.json` (agentType/description/toolUseId)
2. macOS zsh 默认 `cp` 是 `cp -i` alias，shell pipeline 中会卡住 — 用 `/bin/cp` 绕过；commit split 时备份+恢复测试文件比 200 行 Edit 安全
3. `Path.iterdir` monkeypatch 安全（pytest 的 tmp_path 清理用 unlink/stat 不用 iterdir），但 `Path.stat` monkeypatch 会破坏 pytest cleanup — 测 sort key 时直接调 helper 而非 patch

**Next Steps**:
- 24 commits 待 push（包括 d7ddfeb Path-1 / 6f2f7f0+23f478e Path-2）
- 等 instinct loop 24h 观察结果（2026-07-24 装 launchd，今天应该 review）

**Recorded**: yes — Path-2 详情 + commit split 技巧 → auto-memory project-conversation-mirror-path1-shipped.md

### S35 (2026-07-21 01:30~05:10) [vibesop-py] 文档全审计 + Dashboard 依赖重构 + 修复 CI → v8.0.0 PyPI 发布

- [x] **文档全审计**：87 个 MD 文件逐行检查，发现版本分裂（15+ 文件声称 4.x~6.2，实际 8.0.0）、测试数矛盾（2,972 vs 4,066）、架构描述不一致（10 层 vs 4 阶段级联）
- [x] **文档修复**：归档 11 个历史文件、删除 2 个重复文件、更新 26 个文件（版本号、pip→uv、10 层→4 阶段级联、测试数统一）
- [x] **Dashboard 依赖**：`fastapi` + `uvicorn` 从 optional extra 移入 core deps，全局安装后 `vibe dashboard` 开箱即用
- [x] **修复 CI**：29 个 ruff lint 错误（含格式）、3 个 Windows 测试失败（atomic_writer 编码 + tick lock FileExistsError + lock 文件残留）
- [x] **PyPI 发布 v8.0.0**：Release workflow SHA 过期 → 改为 version tag；PyPI Trusted Publisher 配置通过；全 8 CI job 绿色
- [x] **cmspark analytics**：`vibe init` 旧项目无 config.toml → analytics 默认 false → dashboard 空；手动创建 config 启用

**Key Discoveries**:
1. GitHub Actions 的 pinned SHA 会被 GC，非安全关键 action 应用 version tag（`@v2`、`@release/v1`）
2. Windows 上 `Path.read_text()` 默认编码是 locale（CP1252），非 UTF-8 → 跨平台必须显式 encoding
3. Windows 上 `O_CREAT | O_EXCL` 锁文件 close 后残留磁盘 → 需显式 unlink
4. `softprops/action-gh-release` v2.6.2 SHA 和 v2.2.0 SHA 全部不可解析 → `@v2` tag 是唯一稳的

**Next Steps**:
- Dashboard 全局工具重装：`uv tool install --reinstall /path/to/vibesop-py`
- 后续版本升级时确保 config.toml 中的 analytics 设置不被覆盖

**Recorded**: yes — 3 technical pitfalls + 1 reusable pattern → project-knowledge.md
