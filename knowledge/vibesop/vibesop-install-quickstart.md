---
name: vibesop-install-quickstart
description: VibeSOP 安装与快速开始 — uv/pipx 安装、quickstart 向导、doctor 环境检查、LLM API key 配置（Anthropic/OpenAI/Ollama）与无 LLM 降级
type: domain_knowledge
tags:
  - vibesop
  - install
  - quickstart
  - llm-config
---

# VibeSOP 安装与快速开始

## 安装方式

推荐用 uv 或 pipx 安装为独立 CLI 工具：

```bash
# uv（推荐）
uv tool install vibesop

# pipx
pipx install vibesop

# 从源码（开发者）
git clone <repo> && uv sync --extra dev
```

要求 Python 3.12+。升级用 `uv tool install --force --no-cache vibesop`（注意 `--no-cache`：uv 会复用缓存的旧 wheel，这是常见升级不生效的坑）。

## 首次使用：三步走

```bash
# 1. 交互式初始化（向导式，配置平台和 LLM）
vibe quickstart

# 2. 环境体检——检查 LLM key、平台、hooks 配置
vibe doctor

# 3. 试一次路由
vibe route "帮我获取茅台最近一年的股价"
```

交互向导默认不装第三方包。可选一步 `Install OMX (oh-my-codex skills + CLI)?`（默认 No）；Yes 会装 omx 技能包并 best-effort 安装 `omx` CLI。`vibe quickstart --force` 跳过这一步。

新用户也可以用 `vibe onboard` 走新手引导。

## LLM 配置（重要）

**VibeSOP 作为 CLI 子进程运行，不能复用宿主 Agent 的内部 LLM**（比如 Claude Code 会话里的模型）。必须单独配置一个 LLM API key 或本地服务：

```bash
# Anthropic Claude（推荐）
export ANTHROPIC_API_KEY=sk-ant-...

# 或 OpenAI 系（GPT/Kimi 等）
export OPENAI_API_KEY=sk-...

# 或本地 Ollama（零成本，无网络）
vibe config set llm.provider ollama
```

**无 LLM 时会怎样**：降级到关键词/TF-IDF 匹配，简单查询还能用，长查询、中文模糊表述的命中率会明显下降。生产使用强烈建议配 LLM。

## 安装第一个技能

```bash
# 从信任名单或任意 GitHub 仓库安装
vibe install tushare
vibe install https://github.com/user/skills

# 安装时自动做三件事：安全审计 → 智能自动配置 → 同步到平台
```

传统流程要 8 个手动步骤（clone → 读文档 → 写配置 → 设环境变量…），VibeSOP 压缩成一条命令。

## 部署到你的 AI Agent

```bash
# Claude Code（shell hooks 自动触发路由）
vibe build claude-code --output ~/.claude

# Grok Build
vibe build grok-build --output ~/.grok

# Kimi CLI / Pi / OpenCode
vibe build kimi-cli --output ~/.kimi-code
vibe build pi --output .pi
```

部署后在 Agent 里自然说话即可，hook 会在 UserPromptSubmit 时自动路由并注入技能指令。`vibe doctor` / `vibe verify grok-build` 可检查配置健康度。

**Windows + Grok/Pi**：`uv tool install` 把 `vibe.exe` 放到 `%USERPROFILE%\.local\bin`。该目录必须在**用户 PATH** 里，改完后重启 Grok（JSON hook 裸调 `vibe`，没有 bash 的 PATH 修补）。不要把 Kimi/Grok 自带的 `config.toml` 或 Pi 的 `settings.json` 当成已经装好 VibeSOP。

## 常见初次问题

- **路由没反应**：跑 `vibe doctor`，最常见是 LLM key 没配、hooks 没部署
- **Windows 能用吗**：能，一等公民支持（CI 双平台门禁）
- **数据存哪**：全部本地——全局配置在 `~/.vibe/`（config.toml 等），项目级数据在项目根 `.vibe/`，无云端依赖
