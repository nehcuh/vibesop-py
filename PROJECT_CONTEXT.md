# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-08-27 S49 [vibesop-py] pull-20260827 三路评审 → M1/M2 hook 修复闭环

**Session Summary**:
- 拉取 `f1f34de..e286e67`（v8.1.1 上游）三路评审出 M1（rebuild rewrite 破坏用户 hook 条目）/ M2（verify 误报用户 PowerShell 命令）
- fix-plan 4 轮 pi+grok 双路（双 REJECT×2 → 拆分架构 → v4 双 APPROVE）→ v4.1 实施 `utils/hook_commands.py`：宽松 classify 服务 verify、strict parse + legacy-signal 只服务 rewrite
- omx 双 lane 清 3 条一行级；push `574349c`（代码）+ `8304e9a`（CHANGELOG 回填）
- 重部署 `~/.claude` + `~/.grok`(rules+hooks)：UPS route 复活 + route hook 实测点火 exit 0 + 双平台 verify 全绿

**Key Decisions**:
- 识别器与生成器必须同构（win32 规范 1-token / 含空格用户名 / 大写盘符是必测形态）
- shlex `posix=False` 认引号但保留引号字符——宽松口径过剥 fail-safe，严格口径不确定即 None
- 双 APPROVE 后 NIT 按处方折叠不再送审（防无限轮）

**Next Steps**:
1. 8.1.2 待办：C1 白名单 canary 测试；C2 preserve-matcher substring → `command_basenames` 精确匹配
2. 等 CI run 结果（Ubuntu + Windows 矩阵验证 HIGH 修复）
3. Grok 真实会话 probe（gate42/43 cron 8-31 / 9-7）

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
1. ~~重启 Claude Code 验证~~ S49 已重部署 + 实测点火；`SessionStart:startup` 商店 python 是 cmspark pentest hook（已清）
2. 未打 `v8.1.1` tag / 未发 PyPI；Kimi 真目录 `vibe build` 仍可选
<!-- handoff:end -->
