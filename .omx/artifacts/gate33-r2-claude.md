# Gate 33 Round-2 复审结论：**PASS_WITH_NITS**

工作树与所给 diff 已逐文件核对一致(tool_sequences.py / sequence_cmd.py / main.py / grok_build.py / 4 个测试文件 / CHANGELOG / CLI_REFERENCE);无 diff 外夹带改动(`.vibe/skill-index.json` 为生成物)。

## Round-1 findings 闭环验证(全部闭环)

| # | Finding | 证据 |
|---|---------|------|
| BLOCK-1 | camelCase 载荷兼容 | `[inspected]` tool_sequences.py:112/115 接受 `toolName`/`sessionId` + snake + 裸 `tool`;`[executed]` 单测 + 真实 vibe 二进制 e2e(test_capture_end_to_end_via_cli,PASS 非 skip)写入 `search_replace`/`grok-session-1`,toolInput 不泄漏 |
| MAJOR-2 | CLI 路径心跳 | `[inspected]` tool_sequences.py:126-132 采集成功后写 `tool_sequences.last`,OSError→debug;drop 不写(test_drop_writes_no_heartbeat) |
| MAJOR-3 | 根解析三级回退 | `[inspected]` sequence_cmd.py:87-101 flag→env→payload→cwd;`[executed]` 3 个回退测试(payload 赢 cwd / env 赢 payload / cwd 兜底) |
| NIT-6/MAJOR-2 | `vibe route --hook` 落地 | `[executed]` 真实运行(工作树 `uv run vibe`):camelCase `userPrompt` 载荷 → 完整信封(systemMessage + hookSpecificOutput.additionalContext + UserPromptSubmit)exit 0;空 stdin → `{}` exit 0;无参数 → exit 1 带提示。部署的 vibesop-route.json 命令(grok_build.py:188)未变且现已合法 |
| NIT-5/NIT-1 | 测试改真实形状 | `[executed]` 93/93 通过：grok e2e 用真实 camelCase 信封 + `_hermetic_config`,含心跳与 toolInput 不泄漏断言；核心层 3 测 + 根解析 3 测 + --hook 模式 5 测 |
| NIT-2 | 三平台 docstring | `[inspected]` sequence_cmd.py:1-10 ✓ |
| 错误前提更正 | grok_build.py:99-105 / CHANGELOG / CLI_REFERENCE:332,335 | ✓ 全部改为 camelCase 双格式表述 |
| NIT-4 | 工具名词汇推迟 | 理由记录在案(M3 跨平台比较会被词汇差异稀释 + 映射表漂移风险)，合理推迟 |

## 复审重点逐项

1. **`--hook` 位置与副作用** — main.py:593 分支位于函数体首个逻辑点(IntentInterceptor:666、AgentRuntime:712 之前)，前置仅有 import,无路由状态副作用。query 可选化对既有调用兼容(93 测试含全部 route 旧测)。输出用 `print()` 而非 Rich console,避免换行破坏 JSON(与 main.py:691 既有约定一致)。与 shell 模板逐点 parity:query 键序(prompt/user_prompt/query/message/text + userPrompt 追加)、session 双键、纯文本回退、空输入 `{}`、非 dict JSON 当原文 query(shell jq 的 `else empty` + `$INPUT` 回退同语义)。
2. **心跳写在采集之后** — tool_sequences.py:124-132:先落 capture 再写心跳，OSError 降级够用(父目录已在 ：122 mkdir,残余失败模式均为 OSError 子类；非 OSError 异常也会被 CLI 外层 sequence_cmd.py:82 兜住，采集已落盘、仍 exit 0)。shell 模板自身的心跳写入(:88)与新 CLI 心跳同值双写，无冲突。
3. **根解析顺序** — env 优先于 payload 正确：claude 的 `CLAUDE_PROJECT_DIR` 是宿主逐 hook 进程注入的权威值；grok 的 `GROK_WORKSPACE_ROOT` 注入未实证，但缺席时安全滑落到 payload `workspaceRoot`/`cwd`(grok 信封必带)。`_sequences_enabled(root)` 用解析后的根读取，正确。shell 模板显式传 flag,flag 优先，一致。
4. **闭环** — 见上表，7 项 actionable 全闭环，1 项有据推迟。

## 新 Findings(全部 NIT,不阻塞)

- **NIT-1** `src/vibesop/cli/main.py:598-629` — hook 模式用 `AgentRuntime()`(默认 root=进程 cwd),既没有 record-tool 新得的 `_resolve_hook_project_root`,也没有 shell 模板的向上 walk——route 侧状态(spans / missed-query inbox / session 种子)落在 spawn cwd。这是 MAJOR-3 同类问题在 route hook 的残留实例，且 `vibe route --hook` 此前是死命令、gate33 才首次激活该行为。判 NIT 而非 MAJOR 的理由：CHANGELOG 已把 cmspark probe 设为上线条件、round-1 范围明确限定 record-tool。建议：probe 清单加一条“route spans 落在项目 `.vibe/`”,或直接复用已解析的 payload `workspaceRoot` 构造 `AgentRuntime(project_root=...)`(payload 就在手边)。
- **NIT-2** 心跳双路径改了 `last_capture_path()` docstring(tool_sequences.py:82-87)但两处旧表述漏改:`tool_sequences.py:22-24` 模块 docstring("maintained by the hook template")与 `sequence_cmd.py:135-136` status 命令 docstring("written by the hook template")。纯文档漂移。
- **NIT-3** `src/vibesop/cli/main.py:592,616-618` — 注释/help 宣称"always exits 0",但 `handle_query_for_hook` 内部未捕获异常会 traceback + exit 1(shell 模板 `set -e` 下同样暴露，parity 成立，故仅 NIT):可考虑整体 try/except 后打印 `{}`。

## 上线条件重申

CHANGELOG 的 probe 前置(真实 grok 会话后确认 `.vibe/tool_sequences.jsonl` 在涨、probe 前 M3 不采信 grok 序列数据)维持不变，建议按 NIT-1 把 route 状态落点一并纳入 probe 检查项。

`[executed]` 93 targeted tests + 3 次真实二进制边界执行 + ruff clean;`[inspected]` parity/顺序/异常路径分析。
