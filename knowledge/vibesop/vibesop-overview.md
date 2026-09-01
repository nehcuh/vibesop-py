---
name: vibesop-overview
description: VibeSOP 项目总览 — AI SkillOS 定位、解决什么问题、核心概念（技能全生命周期）、技术栈与关键指标
type: domain_knowledge
tags:
  - vibesop
  - overview
  - skillos
---

# VibeSOP 项目总览

## VibeSOP 是什么

VibeSOP 是一个 **AI SkillOS（技能操作系统）**——面向 AI 编程 Agent（Claude Code、Grok Build、Kimi CLI、Pi、Cursor、OpenCode 等）的技能路由、编排与全生命周期管理系统。一句话：**管理技能的发现 → 安装 → 路由 → 编排 → 评估 → 保留/淘汰全链路**。

PyPI 包名 `vibesop`，当前版本 8.1.3，MIT 协议，Python 3.12+。

## 解决什么问题

AI 编程工具已经足够强大，真正的瓶颈是：

1. **找到正确的工具**——技能/skill/prompt 散落在各处，用户记不住 50+ 个技能的命令
2. **技能无限堆积**——装了不用、质量参差、没有人管生命周期
3. **平台割裂**——每个 AI Agent 一套配置格式，技能无法复用

VibeSOP 的回答：用自然语言表达意图 → 语义路由到最佳技能 → 注入到任何平台的 Agent 上下文 → 持续评估技能健康度。

## 愿景（三句话）

- 不再记忆命令，只需表达意图
- 不再猜测工具，智能匹配最佳
- 不再学习平台，一次掌握所有

## 核心概念

### SkillOS 三层架构

1. **技能发现层**——内置技能（`core/skills/`）随 wheel 分发；外部技能通过 `vibe install` 从 GitHub 安装，带自动安全审计
2. **路由引擎**——语义级 query→skill 匹配（`src/vibesop/core/routing/`）+ hook 拦截（`src/vibesop/hooks/`）
3. **平台适配层**——为每个 AI Agent 生成原生配置（`src/vibesop/adapters/`）：CLAUDE.md、hooks JSON、AGENTS.md、shell 脚本等

### 定位边界

VibeSOP 是 **SkillOS + 轻量引导执行层**：简单任务由 VibeSOP 端到端完成（路由→注入→引导执行），复杂任务交还给 AI Agent 接手。它不做重型 Agent 框架，专注"把正确的技能送到正确的 Agent"。

## 技术栈

- Python 3.12+（现代语法：match/case、`X | None` 联合类型）
- CLI 框架 Typer + Rich（漂亮的终端输出）
- 数据校验 Pydantic v2；配置解析 ruamel.yaml/PyYAML；模板 Jinja2
- LLM 集成：anthropic（Claude）与 openai（GPT/Kimi）双 SDK
- 测试 pytest（约 6300+ 用例，覆盖率门禁 73%）；lint ruff；类型 basedpyright；安全 bandit
- 包管理 uv（项目不使用 pip）

## 关键指标与规模

- 路由准确率约 94%（e2e 路由套件实测口径）
- 性能约 44 QPS（目标 40+）
- CI：GitHub Actions，Ubuntu + Windows 双平台、Python 3.12/3.13 矩阵，全绿
- 内置 7 种编排模式：SEQUENTIAL、PARALLEL、FAN_OUT、ADVERSARIAL、LOOP_UNTIL_DRY、TOURNAMENT、PROMPT_CHAIN

## 从哪里了解更多

- 项目 README：快速开始、平台支持矩阵、CLI 参考
- `docs/PHILOSOPHY.md`：设计哲学
- `docs/USE_CASES.md`：12 个具体使用场景
- `docs/skill-format-spec-v3.md`：SKILL.md v3.0 技能格式规范
- CHANGELOG.md：完整版本历史
