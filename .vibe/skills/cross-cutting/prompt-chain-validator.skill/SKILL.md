---
id: prompt-chain-validator
name: Prompt Chain Validator
description: 为复杂功能生成多阶段 Claude Code Prompt Chain，并在 Linux 容器中端到端验证已实现的正确性
version: 1.0.0
type: cross-cutting
author: VibeSOP Team
namespace: cross-cutting
intent: 为复杂功能生成分阶段提示词链并自动容器验证
trigger_when: >
  用户需要为复杂功能生成结构化实现计划，
  或多文件跨模块特性开发，或要求端到端容器验证
triggers:
  - prompt chain
  - 提示词链
  - 分阶段实现
  - 容器验证
  - 端到端验证
  - phased implementation
  - multi-phase prompt
tags:
  - meta-workflow
  - prompt-chain
  - container-validation
  - e2e-testing
  - dynamic-workflow
keywords:
  - prompt chain
  - claude code prompt
  - 容器验证
  - cross-cutting
capabilities:
  - code-analysis
  - prompt-generation
  - container-orchestration
  - integration-testing
category: development
priority: 60
lifecycle: active
scope: project
enabled: true
dependencies:
  - container-runtime
  - jinja2
depends_on:
  - builtin/architect
  - builtin/implementer
  - builtin/red_team
  - builtin/reviewer
confidence: 0.85
commands:
  - vibe prompt-chain diagnose
  - vibe prompt-chain generate
  - vibe prompt-chain validate
  - vibe prompt-chain run
user_invocable: true
steps:
  - skill: builtin/architect
    intent: 扇出读取 10-15 个核心文件，输出问题清单 + 依赖图
    order: 1
    phase: diagnose
  - skill: builtin/implementer
    intent: 按依赖顺序生成分阶段提示词文件，每阶段独立可执行
    order: 2
    phase: generate
  - skill: builtin/red_team
    intent: 创建 Linux 容器，执行验证清单（apt/uv/pytest/hook），输出 JSON 报告
    order: 3
    phase: validate
  - skill: builtin/reviewer
    intent: 审查安全风险、向后兼容性、测试覆盖率
    order: 4
    phase: review
---

# Prompt Chain Validator

为复杂功能生成多阶段 Claude Code Prompt Chain，并在 Linux 容器中端到端验证已实现的正确性。

## 问题

开发复杂特性时，直接让 AI Agent 一次性修改所有文件容易导致：
- 上下文窗口溢出，忽略已有逻辑
- 测试覆盖不足，集成时才发现阻断性 Bug
- 无阶段划分，回滚粒度太粗
- 宿主环境与目标环境不一致（macOS vs Linux）

## 解决方案

按 **Dynamic Workflow Prompt Chain** 模式，将特性开发分为 6+1 个阶段：

| 阶段 | 名称 | 目标 |
|:---:|:---|:---|
| Phase 0 | 扇出诊断 | 读取 10-15 个核心文件，输出问题清单 + 依赖图 |
| Phase 1 | 核心数据模型 | 实现语义分析引擎与核心数据模型 |
| Phase 2 | 编排组合层 | 实现调度、组合、协作逻辑 |
| Phase 3 | 技能分配层 | 实现 per-agent 技能选择与隔离 |
| Phase 4 | 集成串联 | 串联所有模块，修改入口文件 |
| Phase 5 | CLI 增强 | 增强用户体验、添加交互输出 |
| Final | 端到端验证 | Linux 容器内安装 Agent → 配置 hook → 执行真实场景 |

每个阶段输出一个独立的 `.md` 提示词文件，可直接喂给 Claude Code。

## 工作流

```yaml
name: prompt-chain-validator
description: 生成提示词链并在容器中验证
strategy: sequential
stages:
  - name: diagnose
    description: 扇出读取核心文件，输出问题清单
    required: true
    metadata:
      skill: builtin/architect

  - name: generate
    description: 生成分阶段提示词文件
    dependencies: [diagnose]
    required: true
    metadata:
      skill: builtin/implementer

  - name: validate
    description: 创建 Linux 容器，执行端到端验证
    dependencies: [generate]
    required: false
    metadata:
      skill: builtin/red_team

  - name: review
    description: 审查安全、兼容性、覆盖率
    dependencies: [validate]
    required: false
    metadata:
      skill: builtin/reviewer
```

## 使用方式

```bash
# 快速开始：一步生成 + 验证
vibe prompt-chain run "为 VibeSOP 增加 Multi-Agent Squad 能力"

# 分步执行
vibe prompt-chain diagnose "Multi-Agent Squad" --files="src/core/*.py,src/agent/*.py"
vibe prompt-chain generate "Multi-Agent Squad" --output-dir="./prompts"
vibe prompt-chain validate --container=orbstack --prompts-dir="./prompts"

# 查看生成的提示词
ls prompts/
# → phase-0-diagnosis.md
# → phase-1-core-data-model.md
# → phase-2-orchestration.md
# → ...
# → final-e2e-validation.md
```

## 提示词链格式

每个提示词文件遵循标准模板，包含：

| 区块 | 说明 |
|:---|:---|
| 前置条件 | ✅ 上一阶段输出清单 |
| 任务 | 1-2 句话描述本阶段目标 |
| 必须读的文件 | 文件路径 + 关键行号 + 阅读目的 |
| 需求 | 子需求列表，含接口签名、数据模型 |
| 实现要点 | 关键决策表（要点 → 实现方式） |
| 验证标准 | 可自动化的 checklists |
| 输出 | 要求输出的具体文件列表 |

## 容器验证协议

| 阶段 | 操作 | 验证项 |
|:---|:---|:---|
| setup | 创建 Ubuntu 22.04 容器 | orbstack/docker 可用 |
| install | apt + uv sync + npm install | 依赖全部就绪 |
| build | vibe build claude-code | hook 文件生成 |
| test | pytest 核心测试 | 全部通过 |
| e2e | vibe route 5 种模式 | 输出匹配期望模式 |
| hook | echo query \| hook script | 返回 plan JSON |
| report | 汇总结果 | JSON 验证报告 |

## 角色定义

| 角色 | 职责 |
|:---|:---|
| 诊断者 | 读取代码库，输出问题清单和依赖图 |
| 提示词作者 | 生成分阶段提示词，确保每个 prompt 可独立执行 |
| 验证者 | 创建容器，执行验证清单，输出 JSON 报告 |
| 审查者 | 检查安全风险、向后兼容性、测试覆盖率 |
