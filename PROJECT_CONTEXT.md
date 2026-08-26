# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-08-26 S48 [vibesop-py] Claude Code Windows hook — POSIX command + uv-tool Python

**Session Summary**:
- `efcd0cf` 包 `"C:/Program Files/Git/bin/bash.exe"` 仍 127（`bash -c` 空格拆开）→ quoted POSIX path；verify 禁 `\` / `bash.exe`；push `e467519`
- 脚本跑通后报商店 `python3` stub：uv-tool 在 `%APPDATA%\uv\tools\vibesop\Scripts\python.exe`，模板只查 Unix `bin/python`。跳过 WindowsApps；`/tmp` 烟雾 exit 0；push `2c72fd7`
- rebuild `~/.claude`；`vibe verify claude-code` 8/8

**Key Decisions**:
- 宿主已提供 Git Bash，不要再包 `Program Files/Git/bin/bash.exe`
- 烟雾 = `bash -c <settings.json 原样 command>` + stdin；Python 烟雾要从无项目根的 cwd 跑
- 不要 `uv run` 于随机 cwd（会拉临时环境卡住）

**Next Steps**:
1. 重启 Claude Code：UserPromptSubmit 走 vibe-route；`SessionStart:startup` 商店 python 是 cmspark pentest hook（已清）/ Black-cat 已改 shim
2. Grok JSON hook：本会话 shell PATH 无 `~\.local\bin`，考虑绝对路径
3. 未打 `v8.1.1` tag / 未发 PyPI；Kimi 真目录 `vibe build` 仍可选

### 2026-08-26 S44–S47 [vibesop-py] v8.1.1 Windows grok-build 宿主部署 + 平台不变量

**Session Summary**:
- Windows `vibe quickstart`：向导无 grok-build、YAML traceback、二次 install 报 No hooks
- 本机部署 `~/.grok`；User PATH 加 `~\.local\bin`；`vibe verify grok-build` 5/5
- `_is_configured` 只认 VibeSOP 标记；`docs/dev/platform-invariants.md`；push `8af7546`

**Key Decisions**:
- Docker e2e 绿 ≠ 宿主 hook 能跑；平台名单禁止 `len >= 2`
- 「已安装」= `vibesop-route.*`（或 grok `rules/routing.md`）
- bash PATH 修补不传给 JSON/Node/TS spawn-`vibe`

**Next Steps**:
1. 重启 Grok 确认 `/hooks`；可选 `vibe build kimi-cli` 对真实 `~/.kimi-code`
2. PyPI：打 `v8.1.1` tag；挂账 cursor / OpenCode timeout
<!-- handoff:end -->
