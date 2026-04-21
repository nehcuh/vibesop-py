# VibeSOP .skill 文件格式规范 v2.0

> **更新内容**: 添加 LLM 配置和多来源支持

## 概述

`.skill` 文件是 VibeSOP 的**单文件技能分发格式**，包含技能的所有定义、元数据和 LLM 配置，支持一键安装。

---

## 📦 文件结构

```
tushare.skill (tar.gz)
├── SKILL.md           # 技能定义（必需）
├── config.yaml        # 默认配置（可选）
├── llm.yaml          # LLM 配置（可选）
├── requirements.txt   # Python依赖（可选）
├── hooks/            # 钩子脚本（可选）
│   ├── pre_install.sh
│   └── post_install.sh
└── tests/            # 测试文件（可选）
    └── test_skill.py
```

---

## 🆕 SKILL.md 格式 v2.0

### 完整示例

```markdown
---
# 基本信息
id: code-reviewer
name: AI Code Reviewer
description: 使用 Claude 进行智能代码审查
version: 1.0.0
author: Your Name <email@example.com>
namespace: external
tags: [code-review, claude, quality]
skill_type: prompt

# 🆕 LLM 配置
llm_config:
  # 必需的提供商
  provider: anthropic
  
  # 推荐模型（按优先级）
  recommended_models:
    - claude-sonnet-4-6-20250514  # 最优
    - claude-3-5-sonnet-20241022  # 备选
  
  # 最小要求
  min_requirements:
    context_window: 200000
    max_output: 8192
  
  # 默认参数
  default_parameters:
    temperature: 0.3
    max_tokens: 4096
    top_p: 0.95
  
  # 特殊需求
  special_requirements:
    needs_code_context: true
    supports_thinking: true
    prefers_fast_response: false
  
  # 备选方案
  fallback_providers:
    - provider: openai
      models: [gpt-4, gpt-4-turbo]
      reason: "Claude 不可用时"
    - provider: local
      models: [ollama/llama3]
      reason: "本地备选"

# 路由配置
trigger_when: 用户需要代码审查或质量检查
priority: 75
category: review
routing_patterns:
  - .*review.*code
  - .*code.*review

# 依赖和环境
dependencies:
  - pygithub >= 1.59
  - gitpython >= 3.1

env_vars:
  - GITHUB_TOKEN
  - ANTHROPIC_API_KEY

# 🆕 来源配置（可选）
source_config:
  type: official
  repository: vibesop-skills
  registry_url: https://skills.vibesop.dev
  checksum: sha256:abc123...
  signature: <gpg-signature>
---

# AI Code Reviewer

## 技能描述

使用 Claude AI 的强大能力进行代码审查，提供质量反馈和最佳实践建议。

## LLM 需求

此技能需要：
- **提供商**: Anthropic (Claude)
- **推荐模型**: Claude Sonnet 4.6
- **上下文窗口**: 至少 200K tokens
- **温度**: 0.3（确定性输出）

## 自动配置

安装时自动检测 Agent 环境（Claude Code, Cursor 等）：
- ✅ 如果 Agent 有 Claude API，自动使用
- ⚠️ 如果没有，提示用户配置

## 使用示例

### 代码审查

**用户**: "帮我审查这段代码的质量"

**执行**:
1. 分析代码结构
2. 检查最佳实践
3. 提供改进建议

## 配置要求

需要配置 ANTHROPIC_API_KEY 环境变量。
```

---

## 🆕 llm.yaml 配置

### 基本格式

```yaml
# llm.yaml
llm:
  # 提供商和模型
  provider: anthropic
  model: claude-sonnet-4-6-20250514
  
  # API 配置
  api_key_env: ANTHROPIC_API_KEY
  api_base: https://api.anthropic.com
  
  # 参数
  parameters:
    temperature: 0.3
    max_tokens: 4096
    top_p: 0.95
    top_k: 0
  
  # 高级配置
  advanced:
    thinking_enabled: true
    thinking_budget: 16000
    stream: true
  
  # 备选
  fallback:
    provider: openai
    model: gpt-4-turbo
    auto_fallback: true
```

### 环境变量映射

```yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-6-20250514
  
  # 环境变量映射（支持默认值）
  env_mapping:
    ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY:-}"
    ANTHROPIC_BASE_URL: "${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"
```

---

## 🆕 config.yaml 扩展

### 完整配置

```yaml
# config.yaml
# 技能配置
skill:
  id: code-reviewer
  version: 1.0.0

# LLM 配置
llm:
  provider: anthropic
  model: claude-sonnet-4-6-20250514
  auto_detect: true
  fallback_to_agent: true

# 默认配置
defaults:
  priority: 75
  enabled: true

# 路由配置
routing:
  auto_patterns: true
  custom_patterns:
    - .*review.*code

# 执行配置
execution:
  timeout: 60
  max_retries: 3

# 安全配置
security:
  allow_apis:
    - "api.anthropic.com"
  require_env:
    - ANTHROPIC_API_KEY
```

---

## 🆕 支持的来源类型

### 1. 官方仓库

```bash
vibe skill add tushare
```

配置：
```yaml
source_config:
  type: official
  repository: vibesop-skills
  registry_url: https://skills.vibesop.dev
```

### 2. GitHub

```bash
vibe skill add github:user/repo/skills/skill@v1.0.0
vibe skill add https://github.com/user/repo.git
```

配置：
```yaml
source_config:
  type: github
  url: https://github.com/user/repo
  branch: main
  subpath: skills/skill
  tag: v1.0.0
```

### 3. GitLab

```bash
vibe skill add gitlab:user/repo/skills/skill@main
```

### 4. 远程 URL

```bash
vibe skill add https://example.com/skills/skill-1.0.0.skill
```

### 5. 本地文件

```bash
vibe skill add ./skill-1.0.0.skill
vibe skill add --source ./skill.skill --name custom
```

---

## 📋 元数据字段

### 基本信息

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 唯一标识符 |
| `name` | string | ✅ | 显示名称 |
| `description` | string | ✅ | 简短描述 |
| `version` | string | ✅ | 版本号 |
| `author` | string | ❌ | 作者 |
| `namespace` | string | ❌ | 命名空间 |
| `tags` | list | ❌ | 标签 |
| `skill_type` | string | ❌ | 类型 |

### 🆕 LLM 配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `llm_config.provider` | string | ❌ | 提供商 |
| `llm_config.recommended_models` | list | ❌ | 推荐模型 |
| `llm_config.min_requirements` | dict | ❌ | 最小要求 |
| `llm_config.default_parameters` | dict | ❌ | 默认参数 |
| `llm_config.special_requirements` | list | ❌ | 特殊需求 |
| `llm_config.fallback_providers` | list | ❌ | 备选方案 |

### 路由配置

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `trigger_when` | string | ❌ | 触发条件 |
| `priority` | int | ❌ | 优先级 |
| `category` | string | ❌ | 类别 |
| `routing_patterns` | list | ❌ | 路由模式 |

---

## 🔐 安全和签名

### Checksum

```yaml
source_config:
  checksum:
    algorithm: sha256
    value: abc123...
```

### GPG 签名

```yaml
source_config:
  signature:
    method: gpg
    key_id: ABCD1234
    value: <gpg-signature>
    verify_command: gpg --verify
```

---

## 📊 版本控制

使用语义化版本号（Semantic Versioning）：
- **MAJOR.MINOR.PATCH** (如 1.2.3)
- MAJOR: 不兼容的 API 变更
- MINOR: 向后兼容的功能新增
- PATCH: 向后兼容的问题修复

---

## ✅ 验证

### 验证 .skill 文件

```bash
# 检查格式
vibe skill validate skill.skill

# 检查完整性
vibe skill check skill.skill

# 验证签名
vibe skill verify skill.skill --signature
```

---

## 🎯 最佳实践

1. **使用 LLM 配置**: 为需要 LLM 的技能指定配置
2. **提供备选方案**: 配置 fallback_providers
3. **指定最小要求**: 确保兼容性
4. **使用签名**: 验证技能来源
5. **版本控制**: 使用语义化版本号

---

**规范版本**: 2.0
**更新时间**: 2025-04-20
**兼容性**: 向后兼容 v1.0
