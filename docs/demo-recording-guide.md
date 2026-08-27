# Dual-Platform Demo GIF — Recording Guide

> Gate46 块 2 产物。目标：一段两终端并排 GIF，同一句意图在 Claude Code 与
> Grok Build 同时注入生效——「装一次，处处生效」唯一直接可拍的证据。

## Deadline 与降级

- **Deadline**：launch 门（W5）前完成。到期未录 → 降级方案（见下）。
- **降级方案**：`scripts/demo/probe-inject.sh` 的通过输出 + `vibe quickstart`
  注入预览截图，双栏拼接（静态截图对）；或 probe 输出转 asciinema cast。

## 前置（一次性）

```bash
# 1. 两个平台都部署 VibeSOP hook
vibe build claude-code --output ~/.claude
vibe build grok-build --output ~/.grok

# 2. 无头验证注入链路先绿（<10s）
cd /tmp && /path/to/vibesop-py/scripts/demo/probe-inject.sh
# 期望: PROBE PASSED — both platforms inject the same skill
```

## 录制

```bash
# 启动双 pane 布局（tmux）
/path/to/vibesop-py/scripts/demo/dual-platform-demo.sh "help me write a commit message"
```

建议参数（可读性优先）：

- 终端字号 ≥16pt，深色主题，窗口 ≥1400×800（GIF 压缩后仍可读）
- tmux 分屏比例 50:50
- 每句输入后停 1-2s，让路由 + 注入完整出现再继续

GIF 采集任选：

- `t-rec`（`t-rec demo.gif`）或 `asciinema rec` + `agg` 转 GIF
- macOS 系统级： Kap / CleanShot X 的 GIF 模式框选 tmux 窗口

## 必须拍进画面的三个证据（缺一不可）

1. **同句双发**：同一句意图在左右两个 pane 先后输入
2. **双双注入**：两边都出现 `VibeSOP routed: builtin/...` + agent 收到
   `[ACTIVE SKILL: ...]` 上下文
3. **行为变好**：至少一侧 agent 按技能步骤行动（读 SKILL.md / 走 workflow），
   不只是注入发生——这是 HN 第一条负评的预防针

## 录完之后

- 存 `docs/assets/dual-platform-demo.gif`（如超 10MB，用 `gifsicle -O3` 压）
- README 双语首屏嵌入（替换/补充现有静态演示位）
