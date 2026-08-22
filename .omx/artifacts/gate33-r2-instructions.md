# Gate 33 Round-2 复审 — BLOCK/MAJOR 修复验证

## Round-1 结论

- pi:BLOCK — BLOCK-1(grok hook 载荷是 camelCase,与 record_tool_event 的 snake_case 不匹配,实测 100% 静默丢弃;grok 官方文档 + 二进制 strings + 实测三重证据);MAJOR-2(心跳/错误可见性契约缺失);MAJOR-3(项目根靠 spawn cwd);NIT-4(工具名词汇)、NIT-5(e2e 测试编码了错误的 snake_case 形状)、NIT-6(`vibe route --hook` 是非法命令,grok 路由 hook 从未生效)。
- claude:PASS_WITH_NITS 附条件 — MAJOR-1(四个运行时假设全部静默失败无诊断,与 pi BLOCK-1/MAJOR-2/MAJOR-3 同源)、MAJOR-2(同 pi NIT-6,且归因更正:cmspark 的 route span 实际来自 Claude 兼容通道 + routing.md 指示的 in-band 调用);NIT-1(e2e 测试非封闭)、NIT-2(CLI docstring 残留)、NIT-3(_sequences_enabled 三处复制,不强求)。

## Round-2 修复清单(请逐项验证)

1. **BLOCK-1/MAJOR-1a**:`record_tool_event`(src/vibesop/core/instinct/tool_sequences.py)接受 camelCase(`toolName`/`sessionId`)+ 原 snake_case + 裸 `tool`;注释更正错误前提并引 grok 文档。
2. **MAJOR-2/MAJOR-1d**:CLI 路径采集成功写 `tool_sequences.last` 心跳(OSError 降级为 debug);`last_capture_path` docstring 更新双路径。
3. **MAJOR-3/MAJOR-1c**:`record-tool` 根解析 `_resolve_hook_project_root`:显式 flag → `GROK_WORKSPACE_ROOT`/`CLAUDE_PROJECT_DIR` env → 载荷 `workspaceRoot`/`workspace_root`/`cwd` → 进程 cwd。
4. **pi NIT-6 / claude MAJOR-2**:`vibe route --hook` 真正实现(src/vibesop/cli/main.py)——stdin 事件 JSON(5 种 snake query 键 + `userPrompt` + `sessionId`/`session_id`;非 JSON 纯文本回退,与 shell 模板对齐)→ `AgentRuntime().handle_query_for_hook(platform="grok-build", hook_event_name="UserPromptSubmit")` 信封输出;空输入打印 `{}`;永远 exit 0。query 参数变为可选,无 query 且无 --hook 时报错 exit 1。部署的 `vibesop-route.json` 命令不变(现在它合法了)。
5. **pi NIT-5 / claude NIT-1**:grok e2e 测试改用真实 camelCase 信封 + `_hermetic_config` + 新增心跳与 toolInput 不泄漏断言;新增核心层测试(camelCase 记录、心跳、drop 不写心跳)与根解析三级回退测试、--hook 模式 5 例。
6. **claude NIT-2**:sequence_cmd 模块 docstring 改为三平台表述。
7. **错误前提更正**:grok_build.py 注释、CHANGELOG、CLI_REFERENCE 中"grok payload 是 Claude 兼容格式"的说法全部改为" camelCase 信封,双格式兼容"。
8. **pi NIT-4(工具名词汇)**:**推迟**,理由:grok 原生名(search_replace 等)进序列后,M3 行为门的跨平台比较会被词汇差异稀释;但归一化映射表会随 grok 工具集演化漂移,且别名信息在 grok 文档里是 matcher 侧的不是 payload 侧的。记录在案,等 M3 真要做跨平台比较时再定。

## 复审重点

1. `--hook` 分支在 route() 中的位置与副作用(在 IntentInterceptor 之前 short-circuit;query 变可选对既有调用的兼容——测试全绿已覆盖主要面)。
2. record_tool_event 的心跳写在采集之后,OSError 降级是否够。
3. 根解析顺序(env 优先于 payload)是否符合宿主实际注入行为。
4. round-1 所有 finding 是否真正闭环。

## 输出要求

PASS / PASS_WITH_NITS / BLOCK;findings 按 BLOCK/MAJOR/NIT 分级,给文件:行号与理由。
