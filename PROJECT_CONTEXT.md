# Project Context

## Session Handoff

<!-- handoff:start -->

### 2026-07-20 (S33) BOM 修复 + 非交互终端崩溃修复 + Web Dashboard 搭建
**Session**: 用户询问"如何后台可视化历史对话和路由信息" → 发现 `vibe route` 在 Grok Build 中崩溃（BOM + NoConsoleScreenBufferError）→ 修复两个根因 → 搭建 Web Dashboard 回答原始问题。
**Completed**:
- BOM 修复：`encoding.py` 新增 `_strip_bom()` → `read_text_with_fallback()` 和 `load_toml_with_fallback()` 自动剥离 UTF-8 BOM（Windows 编辑器常见）
- 非交互终端保护：`confirmation.py` 新增 `_safe_questionary_select/confirm/text()` → 捕获 `NoConsoleScreenBufferError` → fallback 到默认值 → `main.py` 全部替换
- Web Dashboard：`src/vibesop/dashboard/` — FastAPI 后端（7 API）+ 单页 HTML（4 Tab：Overview/History/Traces/Conversations）+ `vibe dashboard` CLI 命令 + `pyproject.toml` 新增 `dashboard` extra
- 文档同步：CLI_REFERENCE.md 新增 dashboard 章节、ROADMAP.md 标记完成、quality-sprint 计划标记完成
- 测试更新：mock 路径从 `main.questionary` → `main._safe_questionary_select`
**Verification**: 4253 passed, 0 failed (excl. 3 pre-existing)
**Next**: 无紧急任务。Dashboard 后续可考虑：实时刷新、技能健康面板、更多时间范围筛选

### 2026-07-19 (S32) Windows 兼容生产化 — 多 agent 动态工作流
**Session**: Windows 环境从零搭建（uv + Python 3.12）→ 88 failed 基线 → 设计/对抗/开发/评审/验证多 agent 工作流 → 0 failed + CI 全绿。
**Completed**:
- 根因分析（4 agents）：6 桶 88 失败，9 个真实生产 bug；全套文档 `docs/dev/windows-compat/`（01-06 + README）
- P0-P4 开发：编码显式 utf-8 统一 + `utils/encoding.py` locale 回退（治 GBK 自毒）、`utils/symlinks.py` 能力 probe + `.vibe-copy-source` marker、shlex 反斜杠转义+posix、tracker/badges fd 泄漏修（Windows 状态曾永不落盘）、`_isolated_home` 三层测试隔离、CI `test-windows` job
- 评审：双 agent（生产+测试质量）+ pi 两次 SHIP + Grok 独立 SHIP；3 Major 修复（YAML 回退/marker 容错/pin 测试）
- 提交：`a275caa`（主提交）→ CI 首轮抓 `_flatten_skill_name` 反斜杠 bug（probe-skip 盲区）→ `ab9c8df` 修复 → **CI 全绿**（Windows 3.12/3.13 + ubuntu 零回归）→ `4cf9a36` 文档收尾
**Verification**: 本地 4282 passed/0 failed；CI windows-latest + ubuntu 全绿；ruff/basedpyright 0 err
**Next**: ① test-windows 观察期至 ~2026-08-02 后转强约束（删 `continue-on-error`）② 遗留项（05-review.md）：atomic_writer 并发 tmp 碰撞、conftest ClassVar 登记制维护 ③ backlog：Zed adapter、文档深度治理、双 PromptChainGenerator 合并

<!-- handoff:end -->
