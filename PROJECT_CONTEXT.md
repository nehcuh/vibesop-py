# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-04-01 - VibeSOP Python 迁移启动

**会话总结**:
- 创建独立 Python 项目：`/Users/huchen/Projects/vibesop-py`
- 技术栈：uv + Pydantic v2 + Python 3.12+ + Ruff + basedpyright
- 项目结构：src/vibesop, tests/, scripts/
- 已实现：核心模型（SkillRoute, RoutingRequest, RoutingResult, AppSettings）、CLI 框架（route, doctor, version 命令）、路由引擎 stub
- 依赖安装：58 packages via uv sync

**关键决策**:
- 选择独立仓库策略（而非 monorepo）- 完全隔离、无依赖污染
- 使用 uv 而非 pip/poetry - 10-100x 更快
- 使用 Pydantic v2 进行运行时验证和类型检查
- 严格类型检查（basedpyright typeCheckingMode=strict）

**当前状态**:
- ✅ 项目结构和工具链配置完成
- ✅ 核心模型实现（100% test coverage）
- ✅ CLI 基本命令（route, doctor, version）
- 🚧 待修复：24 linting errors（import 排序）、1 test failure（env var 配置）
- 📋 待实现：5 层路由系统、LLM 客户端、技能管理、记忆系统

**下一步**:
1. 修复 linting 错误：`uv run ruff check --fix`
2. 修复 AppSettings 环境变量前缀配置（添加 `env_prefix="VIBE_"`）
3. 实现 5 层路由引擎（AI Triage → Explicit → Scenario → Semantic → Fuzzy）
4. 添加 LLM 客户端（anthropic, openai SDK）
5. 从 Ruby 版本同步核心 YAML 配置

**技术陷阱**:
- P021: uv venv 在项目目录（非全局共享）
- P022: Pydantic-settings 需要配置 `env_prefix`
- P023: Pydantic v2 使用 `ConfigDict` 而非 `class Config`

**可复用模式**:
- RP006: 现代 Python 项目结构（uv + Pydantic v2 + Python 3.12+）
- RP007: Pydantic v2 模型最佳实践（Field(), field_validator, Literal）

<!-- handoff:end -->
