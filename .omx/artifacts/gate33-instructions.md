# Gate 33 复审 — Grok Build PostToolUse 工具序列采集

## 背景

cmspark 用 grok 时发现：路由 span 在涨（UserPromptSubmit hook 正常），但行为证据 tool_call spans 不涨——`GrokBuildAdapter` 只部署路由 hook,PostToolUse 采集只有 claude/kimi 有。grok 原生支持 JSON hooks 的 PostToolUse(cmspark 的 .grok/hooks/impeccable.json 实证），payload 是 Claude 兼容格式（kimi_cli.py:557-567 注释确认 kimi 复用同一形状）。

## 改动（刻意最小）

`src/vibesop/adapters/grok_build.py`:
- 新增 `vibesop-tool-seq.json`:PostToolUse，空 matcher（全工具），命令 = `vibe sequence record-tool`（现成的跨平台 stdin 采集入口，sequence_cmd.py:48，只存 tool+ts+session、永远 exit 0),timeout 10，无 statusMessage（采集不可见）
- `_sequences_enabled()` 开关（与 kimi_cli.py:539-555 同模式，sequences.enabled，默认 true,fail-open)；关则不部署该文件，路由 hook 不受影响
- 纯 JSON hook，无 shell 脚本——保持 grok adapter 的 Windows 原生特性（模块 docstring 第 9 行是其声明的卖点）

测试：tests/adapters/test_tool_seq_hook.py::TestGrokBuildToolSeqHook（渲染包含/开关关闭省略/CLI 端到端采集不泄漏 tool_input)。

文档：CLI_REFERENCE `vibe sequence` 节同步三平台；CHANGELOG 已记。

## 复审重点

1. grok 的 PostToolUse payload 字段名与 `record_tool_event`（接受 tool_name 或 tool、session_id）的兼容性——若 grok 实际字段不同，采集会静默丢（返回 False 不报错）。有没有办法核实/兜底？
2. 空 matcher 在 grok 是否等于"全工具"（对照 vibesop-route.json 的 UserPromptSubmit 空 matcher 惯例与 impeccable.json 的 "Edit|Write|MultiEdit" 形式）。
3. `vibe` 在 grok hook spawn 环境的 PATH 可达性——route hook 已假设（`vibe route --hook`)，本 hook 继承同一假设，是否一致成立。
4. 与 claude/kimi 采集的口径一致性（同一 .vibe/tool_sequences.jsonl,bridge/assemble 消费端无需改动）。

## 输出要求

PASS / PASS_WITH_NITS / BLOCK;findings 按 BLOCK/MAJOR/NIT 分级，给文件：行号与理由。
