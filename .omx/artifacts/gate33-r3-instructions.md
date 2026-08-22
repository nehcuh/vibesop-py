# Gate 33 Round-3 复审（仅 pi) — BLOCK-1 协调确认

## 背景

你 round-2 的 BLOCK-1:复审中途 main.py 被并发改写（加了根解析 + try/except)，而测试桩 `_StubRuntime` 没有 `__init__`,`AgentRuntime(project_root=root)` 抛 TypeError 被吞 → 3 测红。那是复审与修复并发的中间态，不是设计问题。

## 协调结果

1. 测试桩已加 `__init__(**kwargs)` 并捕获 init_kwargs;camelCase 测试新增断言：runtime 以解析后的 project_root 构造（无 workspaceRoot 时 cwd 兜底 = Path())。
2. 你 NIT-C 的两处 docstring 漂移已按建议修复（未回退）。
3. 当前工作树：相关测试 24+93+全量均绿，ruff 双净。
4. 你的 NIT-A/NIT-B 已纳入 probe 范围（见下）。

## probe 清单更新（CHANGELOG 上线条件同步）

cmspark 部署后 probe 确认三件事：(a) 真实 grok 会话后 `.vibe/tool_sequences.jsonl` 在涨；(b) route spans 落在项目 `.vibe/`(NIT-A:原生 UserPromptSubmit hook 是否真的落 span，还是仍靠 Claude 兼容通道/in-band);(c) `vibe sequence status` 心跳正常（NIT-B:PATH 残差由心跳契约暴露）。probe 通过前 M3 不采信 grok 序列数据（维持）。

## 请验证

1. 当前工作树（git diff HEAD）下 tests/cli/test_route_commands.py 等是否全绿。
2. round-2 BLOCK-1 是否解除；NIT-A/NIT-B 的 probe 化处置是否接受。

输出：PASS / PASS_WITH_NITS / BLOCK + 简短理由。
