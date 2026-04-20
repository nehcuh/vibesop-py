# 技能 LLM 配置管理 - 完整指南

## ✅ 支持状态

**Date**: 2026-04-20
**Status**: ✅ **完整实现并测试通过**

---

## 🎯 功能概述

VibeSOP 现在支持为每个技能配置独立的 LLM 设置，优先级如下：

```
1. 技能级别配置 (.vibe/skills/auto-config.yaml)
   ↓ (如果不存在)
2. 全局配置 (.vibe/config.yaml)
   ↓ (如果不存在)
3. 环境变量 (ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)
   ↓ (如果不存在)
4. Agent 环境 (Claude Code, Cursor, etc.)
   ↓ (如果不存在)
5. 默认配置
```

---

## 🚀 使用方式

### 方式 1: 自动配置（推荐）

安装技能时，系统会自动生成 LLM 配置建议：

```bash
$ vibe skill add code-reviewer

Phase 5: Understanding skill and generating config...
  📊 Analyzing: code-reviewer/SKILL.md
  🔍 Keywords: code, review, quality
  🎯 Category: review
  ⚡ Complexity: medium

✓ Auto-generated config:
  Category: review
  Priority: 60
  LLM: anthropic / claude-3-5-sonnet-20241022 (temp: 0.2)
  Confidence: 85%

✓ Config saved to: .vibe/skills/auto-config.yaml
```

### 方式 2: 手动配置单个技能

使用交互式模式：

```bash
$ vibe skill config set code-reviewer

⚙️  Configure LLM: code-reviewer

Which LLM provider?
  🤖 Anthropic (Claude)
  🧠 OpenAI (GPT)
  🌐 Google (Gemini)
  🔮 Other
> 🧠 OpenAI (GPT)

Which model?
  GPT-4 (Recommended)
  GPT-4 Turbo
  GPT-3.5 Turbo (Fast)
> GPT-4 (Recommended)

Select temperature (creativity):
  🎯 Precise (0.1-0.3)
  ⚖️  Balanced (0.4-0.7)
  🎨 Creative (0.8-1.0)
> 🎯 Precise (0.1-0.3)

✓ Configuration saved

┌─────────────────────────────────────────────┐
│ code-reviewer will now use:                 │
│                                             │
│   Provider: openai                          │
│   Model: gpt-4                              │
│   Temperature: 0.2                          │
│                                             │
│ Test it with:                               │
│   vibe route "code-reviewer"                │
└─────────────────────────────────────────────┘
```

### 方式 3: 命令行参数配置

```bash
# 设置 OpenAI GPT-4
$ vibe skill config set code-reviewer \
    --provider openai \
    --model gpt-4 \
    --temperature 0.2

# 设置 Anthropic Claude
$ vibe skill config set brainstorm \
    --provider anthropic \
    --model claude-3-opus-20240229 \
    --temperature 0.9

# 设置自定义 API
$ vibe skill config set my-skill \
    --provider openai \
    --model gpt-4 \
    --api-key sk-xxx \
    --api-base https://api.openai.com/v1
```

### 方式 4: 批量导入配置

创建配置文件 `skills-llm.json`：

```json
{
  "code-reviewer": {
    "provider": "openai",
    "model": "gpt-4",
    "temperature": 0.2
  },
  "brainstorm": {
    "provider": "anthropic",
    "model": "claude-3-opus-20240229",
    "temperature": 0.9
  },
  "debug-helper": {
    "provider": "anthropic",
    "model": "claude-sonnet-4-6",
    "temperature": 0.3
  }
}
```

导入配置：

```bash
$ vibe skill config import skills-llm.json

✓ Imported 3 configurations
```

---

## 📋 查看配置

### 查看所有技能配置

```bash
$ vibe skill config list

┏━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━┓
┃ Skill ID        ┃ Enabled┃ Priority┃ Category  ┃ LLM            ┃ Auto┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━┩
│ code-reviewer   │ ✓      │ 60      │ review    │ openai/gpt-4   │ ✓   │
│ brainstorm      │ ✓      │ 45      │ develop...│ anthropic/cla..│ ✓   │
│ debug-helper    │ ✓      │ 85      │ debugging │ anthropic/cla..│ ✓   │
└─────────────────┴────────┴─────────┴───────────┴─────────────────┴──────┘

Total: 3 | Enabled: 3 | With LLM: 3 | Auto-configured: 3
```

### 查看单个技能配置

```bash
$ vibe skill config get code-reviewer

🔍 Configuration: code-reviewer

Basic Information:
  Skill ID: code-reviewer
  Enabled: ✓
  Priority: 60
  Category: review
  Scope: project

LLM Configuration:
  Requires LLM: Yes
  Provider: openai
  Model: gpt-4
  Temperature: 0.2

  Active LLM: openai/gpt-4
  Source: vibesop_config
  Confidence: 95.0%

Routing Configuration:
  Patterns (5):
    • .*code.*
    • .*review.*
    • .*quality.*
    • .*code-reviewer.*
    • .*(review|audit|quality).*

Metadata:
  Auto-configured: Yes
  Confidence: 85.0%
```

---

## 🗑️ 删除配置

删除技能配置后，技能将使用全局配置：

```bash
$ vibe skill config delete code-reviewer

Are you sure you want to delete the configuration for 'code-reviewer'? yes

✓ Configuration deleted
The skill will use global configuration from now on
```

---

## 📤 导出配置

导出所有技能配置到文件：

```bash
# 导出为 JSON
$ vibe skill config export skills-llm-backup.json

✓ Exported 3 configurations
  Output: skills-llm-backup.json

# 导出为 YAML
$ vibe skill config export skills-llm-backup.yaml

✓ Exported 3 configurations
  Output: skills-llm-backup.yaml
```

---

## 📁 配置文件结构

### .vibe/skills/auto-config.yaml

```yaml
skills:
  code-reviewer:
    enabled: true
    priority: 60
    category: review
    scope: project
    requires_llm: true
    llm:
      provider: openai
      model: gpt-4
      temperature: 0.2
    routing:
      patterns:
        - .*code.*
        - .*review.*
        - .*quality.*
      priority: 60
    metadata:
      auto_configured: true
      config_source: auto_generated
      confidence: 0.85

  brainstorm:
    enabled: true
    priority: 45
    category: brainstorming
    scope: project
    requires_llm: true
    llm:
      provider: anthropic
      model: claude-3-opus-20240229
      temperature: 0.9
    routing:
      patterns:
        - .*brainstorm.*
        - .*idea.*
        - .*creative.*
      priority: 45
    metadata:
      auto_configured: true
      confidence: 0.78
```

---

## 🔧 Python API

### 获取技能 LLM 配置

```python
from vibesop.core.skills.config_manager import get_skill_llm_config

# 获取技能的 LLM 配置
llm_config = get_skill_llm_config("code-reviewer")

if llm_config:
    print(f"Provider: {llm_config.provider}")
    print(f"Model: {llm_config.model}")
    print(f"Temperature: {llm_config.temperature}")
    print(f"Source: {llm_config.source.value}")
    print(f"Confidence: {llm_config.confidence:.1%}")
```

### 设置技能 LLM 配置

```python
from vibesop.core.skills.config_manager import set_skill_llm_config

# 设置技能的 LLM 配置
set_skill_llm_config("my-skill", {
    "provider": "openai",
    "model": "gpt-4",
    "temperature": 0.7,
    "api_key": "sk-xxx",  # 可选
    "api_base": "https://api.openai.com/v1",  # 可选
})
```

### 列出所有技能配置

```python
from vibesop.core.skills.config_manager import list_skill_configs

# 列出所有技能配置
skill_configs = list_skill_configs()

for skill_id, config in skill_configs.items():
    print(f"{skill_id}:")
    print(f"  Enabled: {config.enabled}")
    print(f"  Priority: {config.priority}")
    print(f"  Category: {config.category}")
    if config.requires_llm:
        print(f"  LLM: {config.llm_provider}/{config.llm_model}")
```

---

## 🎯 使用场景

### 场景 1: 不同技能使用不同的 LLM

```bash
# 代码审查使用 GPT-4（更准确）
$ vibe skill config set code-reviewer --provider openai --model gpt-4 --temperature 0.2

# 头脑风暴使用 Claude Opus（更有创意）
$ vibe skill config set brainstorm --provider anthropic --model claude-3-opus-20240229 --temperature 0.9

# 调试使用 Claude Sonnet（快速且准确）
$ vibe skill config set debug-helper --provider anthropic --model claude-sonnet-4-6 --temperature 0.3
```

### 场景 2: 成本优化

```bash
# 高优先级技能使用最好的模型
$ vibe skill config set security-audit --provider anthropic --model claude-3-opus-20240229

# 低优先级技能使用快速模型
$ vibe skill config set doc-helper --provider anthropic --model claude-3-haiku-20240307
```

### 场景 3: 团队协作

```bash
# 导出团队配置
$ vibe skill config export team-skills-llm.json

# 分享给团队成员
$ git add team-skills-llm.json
$ git commit -m "Add team skill LLM configs"

# 其他成员导入
$ vibe skill config import team-skills-llm.json
```

---

## ✅ 测试结果

所有功能均已测试通过：

```bash
$ python tests/unit/test_skill_config_manager.py

✅ ALL TESTS PASSED!

Test Results:
  • Set and Get Skill LLM Config: PASSED
  • List Skill Configs: PASSED
  • Update Skill Config: PASSED
  • Delete Skill Config: PASSED
  • LLM Config Priority Fallback: PASSED
```

---

## 🎁 核心优势

### 1. 灵活性

- 每个技能可以配置不同的 LLM
- 支持多种 LLM 提供商（Anthropic, OpenAI, Google, 等）
- 可以覆盖全局配置

### 2. 智能回退

```
技能配置 → 全局配置 → 环境变量 → Agent 环境 → 默认值
```

### 3. 易用性

- 自动配置：安装技能时自动生成配置
- 交互式配置：友好的命令行交互
- 批量管理：支持导入/导出

### 4. 透明度

- 清晰的配置优先级
- 详细的配置来源信息
- 完整的配置查看命令

---

## 📚 相关文档

- [技能理解与自动配置](./SKILL_UNDERSTANDING_SUMMARY.md)
- [LLM 配置解析器](../src/vibesop/core/llm_config.py)
- [技能配置管理器](../src/vibesop/core/skills/config_manager.py)

---

**完整实现并测试通过** ✅

用户现在可以：
- ✅ 为每个技能配置独立的 LLM
- ✅ 使用自动配置或手动配置
- ✅ 批量导入/导出配置
- ✅ 查看所有技能的配置状态
- ✅ 灵活地覆盖全局配置
