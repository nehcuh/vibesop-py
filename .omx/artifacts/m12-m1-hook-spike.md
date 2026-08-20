# M12 M1 spike：kimi / pi hook 体系 PostToolUse 可行性

> 日期：2026-08-20。结论先行：**kimi 支持（已实现），pi 支持但未实现（原因见下），
> grok 有独立既有问题（注明，不修）**。

## Kimi Code CLI —— 支持，已实现

证据：

- 官方 hooks 文档（https://moonshotai.github.io/kimi-code/en/customization/hooks）
  事件参考表明确列出 `PostToolUse`（observation-only，matcher=工具名），
  且所有 hook payload 基础字段含 `session_id`、`hook_event_name`、`cwd`——
  与 Claude Code payload 结构兼容。
- hook 命令的工作目录 = 当前 session 的项目目录（同上文档），因此渲染时
  不烤死 project_root，运行时 fallback 到 `$PWD` 即落到工作项目的 `.vibe/`。
- 本仓库适配器此前只注册了 `UserPromptSubmit`
  （src/vibesop/adapters/kimi_cli.py `_generate_config`）。

实现（本里程碑落地）：

- `kimi_cli.py::_render_tool_seq_hook` 复用
  `templates/claude-code/hooks/vibesop-tool-seq.sh.j2`（POSIX sh，无平台耦合），
  以 `project_root=""` 渲染到 `hooks/vibesop-tool-seq.sh`；
- `_generate_config` 追加 `[[hooks]] event = "PostToolUse"` 条目；
- 与 claude 一致受 `sequences.enabled` 开关门控（默认开）。

## Pi Coding Agent —— 支持，本里程碑不实现

证据：

- 扩展 API 存在 `tool_call`（可拦截/阻断）与 `tool_result` 事件，是
  PostToolUse 的等价物。证据：pi.dev 扩展文档
  （https://pi.dev/docs/latest/extensions）、npm 包
  `@earendil-works/pi-coding-agent` README 示例（`pi.on("tool_call", ...)`）、
  第三方教程（nunorralves.pt/posts/2026-06-08-pi-extensions 使用
  `tool_call` / `before_agent_start`）。
- 本仓库 pi 模板只用了 `input` / `session_start` / `session_shutdown`
  （templates/pi/extensions/vibesop-route.ts.j2、vibesop-track.ts.j2）。

不实现的理由：

- `tool_result` 事件的 payload 形状（工具名字段名、是否携带 session id）
  未经实机验证；照猜生成 TS 扩展正是 M12 反对的「装了但零产出」模式。
- pi 走 `vibe route --json` CLI 路径（非 handle_query_for_hook），CLI 每次
  mint 新 UUID（cli/main.py:745），session join 需要 CLI 侧加
  `--session-id` 类入口——超出本里程碑「hook 通道」范围。
- 建议后续里程碑：实机验证 `tool_result` payload 后新增
  `templates/pi/extensions/vibesop-tool-seq.ts.j2`，并为 `vibe route`
  增加 session 前向参数。在此期间 pi 平台按设计文档诚实降级：
  `behavior_evidence=unavailable`。

## Grok Build —— 注明一个既有问题（不在本里程碑修）

- `grok_build.py::_render_hook_json` 生成的 JSON hook 执行
  `vibe route --hook`，但 `vibe route` 命令**没有 `--hook` 选项**
  （cli/main.py:467 起的参数列表中没有）——该 hook 一旦触发即以
  "No such option" 失败。属既有 bug，与 M12 无关，记录待办。
- Grok JSON hooks 仅注册了 `UserPromptSubmit`；是否有 PostToolUse 等价物
  未查得官方文档，暂按「未知」处理。

## 附：claude-code 捕获通道零产出根因（gate15 BLOCK-2）实测结论

- hook 本身能跑：手动 echo 假 payload 调 `~/.claude/hooks/vibesop-tool-seq.sh`
  退出码 0，且 `vibe sequence record-tool` 子命令存在（全局 vibe v8.1.0）。
- **根因是数据落点错了**：hook 装在 `~/.claude/hooks/`（全局），渲染时
  `_tool_seq_project_root` 把 project_root 定为 `$HOME`，于是所有记录都写进
  `~/.vibe/tool_sequences.jsonl`（实测该文件 1.4MB、持续在增长），dogfood
  仓库的 `.vibe/tool_sequences.jsonl` 自然永远是零产出。模板旧逻辑里
  render-time root 优先于 `CLAUDE_PROJECT_DIR`，静默吞错又掩盖了这一切。
- 修复：模板改为 `CLAUDE_PROJECT_DIR`（agent 实际工作项目）优先，
  render-time root 兜底；失败写 `.vibe/hook_errors.log`（64KB 封顶滚动），
  成功刷新 `.vibe/tool_sequences.last` 活性时间戳。
- 已知边界：`record-tool` 对畸形 JSON 静默丢弃且恒退出 0
  （sequence_cmd.py:60-73，另一路负责），因此 shell 侧 rc=0 只代表
  「CLI 跑起来了」，不代表「记录写入」。活性以 `.last` + jsonl 增长双信号
  观测即可覆盖。
