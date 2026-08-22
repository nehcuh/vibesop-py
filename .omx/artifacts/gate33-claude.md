评审完成。以下为 Gate 33 复审报告。

---

# Gate 33 复审裁决：PASS_WITH_NITS

(附 2 个 MAJOR:其一为上线条件，其一为既有问题、非本 diff 引入但动摇了 brief 的推理链)

**已执行验证**：工作树与嵌入 diff 对账一致；`tests/adapters/test_tool_seq_hook.py` 19/19 全过(含 3 个新 grok 测试，e2e 在本机实测采集成功且 `tool_input` 不泄漏)；`vibe route --hook` 实跑 exit 2;全量 `uv run pytest` 未跑(仅 targeted)。

## Findings

### MAJOR-1 — grok hook 的四个运行时假设全部静默失败，且无任何诊断信号

`src/vibesop/adapters/grok_build.py:225-241`(`_render_tool_seq_hook_json`)

JSON hook 相比 claude/kimi 的 shell 版(vibesop-tool-seq.sh.j2)丢掉了全部三层防护：PATH 兜底(j2:19)、失败留痕 hook_errors.log(j2:90)、成功心跳 tool_sequences.last(j2:88)。具体：

- **(a) payload 字段**(复审重点 #1):`record_tool_event` 只认 `tool_name`/`tool` + `session_id`(tool_sequences.py:98-101),不匹配即静默 `return False`,且 CLI 丢弃返回值(sequence_cmd.py:71)。仓内有直接反面证据：host agent 的 envelope 字段名确实不统一——shell 路由 hook 为 query 容错了 **5 种拼法**(`.prompt // .user_prompt // .query // .message // .text`,shared/vibesop-route.sh.j2:17),且 grok 自身遥测风格是 camelCase(`hookEventName`,docs/dev/agent-scenario-validation-2026-07-19.md:152)。kimi 的 Claude 兼容 payload 是实测后文档化的(kimi_cli.py:560-563);grok 的 PostToolUse payload 字段名在本仓**零实证**。
- **(b) 空 matcher**(复审重点 #2):route hook 的空 matcher 不构成先例——UserPromptSubmit 非 tool 事件，matcher 不参与匹配；impeccable.json 证明的是显式 regex(`Edit|Write|MultiEdit`)生效，证明不了空串 = 全工具。唯一依据是“grok 兼容 Claude 语义”，未实证。
- **(c) PATH + cwd**(复审重点 #3):见 MAJOR-2——route hook 先例不成立，`vibe` 在 grok 原生 hook spawn 环境的可达性、spawn cwd 是否为项目目录(kimi 有文档化先例，kimi_cli.py:563-566;grok 无)均未实证。cwd 错则数据散落他处——正是 M12 gate15 BLOCK-2 的原事故类别。
- **(d) 心跳缺失**:`tool_sequences.last` 只由 shell 模板写，grok 永远不会有 → `vibe sequence status` 在 grok 上永远报“从未捕获或 hook 未更新”，即使采集正常。

**缓解(低成本，建议随本 gate 或紧随其后)**：① `record-tool` CLI 成功落盘后自己写心跳(三平台共享，shell 模板的写法变成冗余但无害)；② `record_tool_event` 接受 `toolName`/`sessionId` 变体，或至少 drop 时留痕；③ **上线条件**：cmspark 部署后做一次 probe——`echo '{"tool_name":"Probe","session_id":"probe"}' | vibe sequence record-tool` + 跑一个真实 grok 会话后确认 `.vibe/tool_sequences.jsonl` 在涨。

### MAJOR-2(既有，非本 diff)— `vibesop-route.json` 的命令从来就是非法的，"UserPromptSubmit hook 正常”的归因有误

`src/vibesop/adapters/grok_build.py:186`:`"command": "vibe route --hook"`。[已执行] 实跑 exit 2 `No such option: --hook`;`--hook` 选项从未存在(`git log -S` 只有引入 commit e9b6f15)。因此 grok 原生路由 hook 自落地起大概率从未通过。cmspark“路由 span 在涨”的真实来源是 **Claude 兼容通道**：grok 触发 `~/.claude/settings.json` 的 UserPromptSubmit → vibesop-route.sh(docs/dev/agent-scenario-validation-2026-07-19.md:150-155 实证)+ routing.md 指示的 in-band `vibe route`。含义：brief 用“route hook 已验证”支撑 PATH/payload 假设的推理不成立，grok 原生 JSON hook 层的端到端行为实际上从未被验证过。建议后续 gate 修复(改调 `agent_runtime.py:748` 的 `handle_query_for_hook`,同 shell 版;或给 CLI 加 `--hook` 模式)。

### NIT

1. `tests/adapters/test_tool_seq_hook.py:342-372` e2e 测试非封闭：没用 `_hermetic_config`(两个兄弟测试都用了)，读真实 `~/.vibe` 配置——开发机全局 `sequences.enabled=false` 或环境带 `VIBE_SEQUENCES_ENABLED=false` 会 flake;且测的是已安装的 vibe 二进制而非工作树代码。
2. `src/vibesop/cli/commands/sequence_cmd.py:3-5,54`:CLI `--help` 与模块 docstring 仍写 "Claude Code PostToolUse hook";CLI_REFERENCE 已同步，CLI 自身文案漏了。
3. `_sequences_enabled` 现已三处复制(kimi_cli.py:539 / grok_build.py:196 / sequence_cmd.py:30)。已成型模式，不强求；出现第 4 处前值得提取。

## 四个复审重点逐条回答

1. **payload 兼容**：仓内无法核实 grok 实际字段；有反面先例(字段名跨 agent 不统一 + grok camelCase 风格)。兜底 = 别名容错/drop 留痕 + 上线 probe(见 MAJOR-1)。
2. **空 matcher**:与 route hook 惯例形式一致，但该惯例本身从未被证明生效过；只能靠 probe 兜底。
3. **PATH 一致性**：不成立——route hook 的命令本身非法，它没有验证过任何东西；claude/kimi shell 版自兜 PATH 恰恰说明 host agent spawn 环境不可信。
4. **口径一致性**：✓ 同一 record-tool 入口、同一 `{tool,ts,session}` schema、同一 `.vibe/tool_sequences.jsonl`,bridge/assemble 按文件游标消费无需改动 `[已检查]`;timeout 10 与 kimi 一致(kimi_cli.py:196);开关语义与 kimi 逐行同构；全局 hook(`~/.grok`,renderer.py:94-95)结构上只能依赖 spawn cwd,设计选择合理。

**结论**：可验证范围内全部正确、测试绿；但本 gate 的原始动机(“采集为何不涨查不出来”)在 JSON hook 上会原样复现——静默失败三连无诊断。按 gate24 惯例 MAJOR 附条件放行：**cmspark probe 通过前，M3 行为门不得把 grok 的 tool_sequences 数据当作有效证据。**
