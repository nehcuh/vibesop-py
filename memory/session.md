
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
