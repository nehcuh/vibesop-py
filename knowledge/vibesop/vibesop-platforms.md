---
name: vibesop-platforms
description: VibeSOP 支持的 AI Agent 平台矩阵 — Claude Code/Grok Build（hooks 自动）、Kimi CLI（config）、Pi（extensions）、Cursor/OpenCode（文件配置）；各平台部署命令与触发机制
type: domain_knowledge
tags:
  - vibesop
  - platforms
  - integration
  - deployment
---

# VibeSOP 平台支持

## 平台矩阵

| 平台 | 工作流编排 | 原生并行 | 触发方式 |
|------|-----------|---------|---------|
| Claude Code | ✅ | ✅ Sub-agents | Auto（hooks） |
| Grok Build | ✅ | ⚠️ Serial only | Auto（hooks） |
| Kimi CLI | ✅ | ⚠️ Serial only | Auto（config） |
| Pi Agent | ✅ | ⚠️ Serial only | Auto（extensions） |
| OpenCode | ✅ | ⚠️ Serial only | Manual |
| Cursor | ✅ | ⚠️ Serial only | 配置生成 |

此外任何支持 SKILL.md 的工具（Continue.dev、Aider 等）都能用开放生态的技能。

## 各平台部署命令

```bash
# Claude Code：shell hooks 在 UserPromptSubmit 自动路由
vibe build claude-code --output ~/.claude

# Grok Build：hooks 自动路由 + PostToolUse 工具序列采集
vibe build grok-build --output ~/.grok

# Kimi CLI：config hooks 自动触发
vibe build kimi-cli --output ~/.kimi-code

# Pi Agent：TypeScript extensions 自动触发
vibe build pi --output .pi

# OpenCode：手动 source 环境后启动
vibe build opencode --output ~/.config/opencode

# 一次部署所有平台
vibe build --platform=all
```

## 触发机制说明

- **hooks 级**（Claude Code / Grok Build）：Agent 的生命周期事件（用户提交提示、工具调用后）直接回调 VibeSOP，零操作成本，还能反向采集工具序列供 instinct 学习
- **config 级**（Kimi CLI）：配置文件内声明的自动触发
- **extensions 级**（Pi）：SDK 内嵌，进程内直调
- **file 级**（OpenCode / Cursor）：生成配置文件，Agent 启动时装配；OpenCode 需手动 source

## 一次定义，所有平台

技能作者只写一份 SKILL.md（v3.0 规范），平台差异全部由 adapter 层（`src/vibesop/adapters/`）消化：Hook-based（Claude Code/Grok）、File-based（Kimi/Cursor/OpenCode）、SDK-based（Pi）。新增平台走 conformance suite（85 测试）自证合规。

## 常见问题

- **装了技能但 Agent 里没反应**：先 `vibe doctor` 看该平台 hooks/config 是否部署成功；再确认技能已 `skills sync` 到对应平台
- **多平台并存**：支持。各平台配置互不干扰，共享同一技能池与偏好数据
- **升级后行为没变**：`uv tool install --force --no-cache vibesop` 后重新 `vibe build`（uv 缓存 wheel 会装旧版）
