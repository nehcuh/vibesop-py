---
name: vibesop-architecture
description: VibeSOP 三层架构与代码组织 — 技能发现/路由引擎/平台适配器、关键目录表、SKILL.md v3.0 规范（29 字段+85 conformance 测试）、三种 adapter 集成模式
type: domain_knowledge
tags:
  - vibesop
  - architecture
  - adapters
  - spec
---

# VibeSOP 架构

## 三层架构（3-pillar）

VibeSOP 的架构可以概括为三根支柱：

| 支柱 | 职责 | 载体 |
|------|------|------|
| **The Spec** | 规范的 SKILL.md v3.0 格式 | `spec/models.py`，29 个字段，`SpecValidator` 校验 |
| **The Reference** | 三种平台集成模式 | File-based / Hook-based / SDK-based adapter |
| **The Conformance Suite** | 任何平台可自证合规 | 85 个测试，`vibe spec conformance --all` |

运行时链路：**技能发现 → 路由引擎 → 平台适配**。用户的 query 进路由引擎，匹配到技能后，由平台适配层把技能指令注入对应 AI Agent 的上下文。

## 关键目录

| 目录 | 用途 |
|------|------|
| `src/vibesop/core/` | 核心：路由、分类、技能注册表 |
| `src/vibesop/cli/` | Typer CLI 命令 |
| `src/vibesop/adapters/` | 平台适配器（claude-code、grok-build、kimi-cli、pi、cursor、opencode） |
| `src/vibesop/installer/` | 技能安装与生命周期 |
| `src/vibesop/builder/` | 平台配置生成与渲染 |
| `src/vibesop/agent/` | 进程内 Agent 集成 API（IntentInterceptor / SkillInjector / DecisionPresenter / PlanExecutor） |
| `src/vibesop/hooks/` | 基于 hook 的请求拦截 |
| `src/vibesop/utils/` | 编码、符号链接、Jinja 安全、原子写入、文件锁 |
| `core/skills/` | 内置技能（随 wheel 分发） |
| `core/policies/` | 策略定义（YAML） |
| `docs/` | 架构文档、ADR、用户/开发者指南 |
| `memory/` | 项目知识库与会话状态（AI 协作记忆） |
| `tests/` | 测试套件（镜像 src 结构） |

## 三种平台集成模式（adapter 模式）

1. **HookBasedAdapter**——生成 shell hook 脚本 + JSON 配置，在 Agent 的 UserPromptSubmit / PostToolUse 等生命周期点自动触发。代表：Claude Code（`~/.claude/hooks/`）、Grok Build（`~/.grok/`）
2. **FileBasedAdapter**——生成静态配置文件（AGENTS.md / config.toml），Agent 启动时读取。代表：Kimi CLI、Cursor、OpenCode
3. **SdkBasedAdapter**——进程内 SDK 集成（TypeScript extensions 等）。代表：Pi Agent

新增平台 = 继承对应基类实现少数方法，conformance suite 验证合规性。

## SKILL.md v3.0 技能格式

技能的规范载体是 SKILL.md 文件（YAML frontmatter + markdown 正文）：

- 29 个字段，`SkillSpec` Pydantic model 定义，`SpecValidator` 校验
- `SkillType` 枚举（含 STANDARD 等类型）
- 一个技能定义同时服务所有平台——平台差异由 adapter 消化，技能作者不用关心
- `vibe spec` 命令族管理规范与合规检查

## Agent Runtime 层

`src/vibesop/agent/` 提供进程内集成 API，四个核心组件：

- **IntentInterceptor**——意图拦截
- **SkillInjector**——技能注入（候选目录含项目/全局 `.vibe/skills`，支持 nested 匹配）
- **DecisionPresenter**——决策呈现
- **PlanExecutor**——计划执行

## 工程质量基线

- 严格类型：basedpyright，所有公开函数带参数/返回类型注解，模块用 `__all__` 显式导出
- 错误处理统一走 `vibesop.core.exceptions` 自定义异常层级
- 原子写入（AtomicWriter：临时文件 + rename）、跨进程文件锁（sibling lock file 约定：`数据文件名 + .lock`）
- ADR 记录架构决策（`docs/adr/`）
