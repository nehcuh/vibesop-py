# VibeSOP 技能来源和 LLM 自动配置方案

## 📋 需求分析

### 1. 来源指定问题
**现状**：`vibe skill add <skill-source>` 只支持基本来源
**需求**：支持更多来源类型和灵活的来源指定

### 2. LLM 配置问题
**现状**：技能定义中没有 LLM 配置，无法自动配置所需模型
**需求**：
- 在 .skill 文件中指定 LLM 需求
- 安装时自动检测 LLM 需求
- 提示用户配置或自动使用 Agent 自带的 LLM

---

## 🎯 方案设计

### Part 1: 扩展来源指定

#### 1.1 支持的来源类型

```bash
# 官方仓库（默认）
vibe skill add tushare

# 本地 .skill 文件
vibe skill add ./tushare-1.0.0.skill

# 本地目录
vibe skill add ./skills/tushare

# 远程 URL
vibe skill add https://example.com/skills/tushare-1.0.0.skill

# Git 仓库
vibe skill add github:user/rebo/skills/tushare@v1.0.0

# GitLab
vibe skill add gitlab:user/repo/skills/tushare@main

# 任何 Git URL
vibe skill add https://github.com/user/repo.git

# 从文件安装（带参数）
vibe skill add --source ./tushare.skill --name my-tushare

# 从 URL 安装（带参数）
vibe skill add --source https://example.com/skill.tar.gz --name custom-skill
```

#### 1.2 来源自动检测

```python
def detect_source_type(source: str) -> SourceType:
    """自动检测来源类型"""
    
    # 官方仓库名称
    if source in OFFICIAL_SKILLS:
        return SourceType.OFFICIAL
    
    # GitHub URL
    if source.startswith("github:") or "github.com" in source:
        return SourceType.GITHUB
    
    # GitLab URL
    if source.startswith("gitlab:") or "gitlab.com" in source:
        return SourceType.GITLAB
    
    # HTTP/HTTPS URL
    if source.startswith(("http://", "https://")):
        return SourceType.URL
    
    # 本地 .skill 文件
    if Path(source).suffix == ".skill":
        return SourceType.LOCAL_FILE
    
    # 本地目录
    if Path(source).is_dir():
        return SourceType.LOCAL_DIR
    
    # 默认：尝试作为官方仓库
    return SourceType.OFFICIAL
```

---

### Part 2: LLM 配置规范

#### 2.1 扩展 SKILL.md 格式

```markdown
---
id: code-reviewer
name: AI Code Reviewer
description: 使用 LLM 进行智能代码审查
version: 1.0.0
skill_type: prompt

# 🆕 LLM 配置
llm_config:
  # 必需的 LLM 提供商
  provider: anthropic
  
  # 推荐的模型（可指定多个，按优先级）
  recommended_models:
    - claude-sonnet-4-6-20250514  # 最优选择
    - claude-3-5-sonnet-20241022  # 备选
  
  # 最小模型要求
  min_requirements:
    context_window: 200000  # 最小上下文窗口
    max_output: 8192        # 最小输出 tokens
  
  # 推荐参数（如果没有指定，使用这些默认值）
  default_parameters:
    temperature: 0.3        # 代码审查需要确定性
    max_tokens: 4096
    top_p: 0.95
  
  # 特殊要求
  special_requirements:
    - needs_code_context: true    # 需要代码上下文
    - supports_thinking: true     # 支持 thinking mode
    - prefers_fast_response: false  # 不需要特别快的响应
  
  # 兼容性（可选的备选方案）
  fallback_providers:
    - provider: openai
      models: [gpt-4, gpt-4-turbo]
      reason: "如果 Claude 不可用"
    - provider: local
      models: [ollama/llama3]
      reason: "本地备选"

# 依赖和配置保持不变
dependencies:
  - pygithub >= 1.59
env_vars:
  - GITHUB_TOKEN
---
```

#### 2.2 config.yaml 中的 LLM 配置

```yaml
# config.yaml
llm:
  # 必需配置
  provider: anthropic
  model: claude-sonnet-4-6-20250514
  
  # 参数配置
  parameters:
    temperature: 0.3
    max_tokens: 4096
    top_p: 0.95
  
  # 环境变量映射
  env_mapping:
    ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY:-}"
  
  # 自动检测
  auto_detect: true
  fallback_to_agent: true  # 如果没有配置，使用 Agent 的 LLM
```

---

### Part 3: 安装时自动检测和配置

#### 3.1 LLM 需求检测

```python
def detect_llm_requirements(metadata: SkillMetadata) -> LLMRequirements:
    """检测技能的 LLM 需求"""
    
    requirements = LLMRequirements()
    
    # 从 metadata 读取 LLM 配置
    if hasattr(metadata, 'llm_config') and metadata.llm_config:
        requirements.provider = metadata.llm_config.get('provider')
        requirements.models = metadata.llm_config.get('recommended_models', [])
        requirements.min_context = metadata.llm_config.get('min_requirements', {}).get('context_window', 0)
        requirements.parameters = metadata.llm_config.get('default_parameters', {})
    
    # 从技能类型推断
    elif metadata.skill_type == SkillType.PROMPT:
        # Prompt 技能默认需要 LLM
        requirements.provider = "anthropic"  # 默认使用 Anthropic
        requirements.models = ["claude-sonnet-4-6-20250514"]
    
    # 从关键词推断
    keywords = metadata.description.lower()
    if any(kw in keywords for kw in ['code', 'review', 'refactor']):
        requirements.min_context = 100000
        requirements.parameters = {'temperature': 0.3}
    elif any(kw in keywords for kw in ['creative', 'brainstorm', 'idea']):
        requirements.parameters = {'temperature': 0.8}
    
    return requirements
```

#### 3.2 Agent 环境检测

```python
def detect_agent_llm() -> LLMConfig | None:
    """检测当前 Agent 环境的 LLM 配置"""
    
    # 检测 Claude Code
    if is_claude_code_environment():
        return LLMConfig(
            provider="anthropic",
            model=get_claude_code_model(),
            api_key=get_claude_code_api_key()
        )
    
    # 检测 Cursor
    if is_cursor_environment():
        return LLMConfig(
            provider="anthropic",
            model=get_cursor_model(),
            api_key=get_cursor_api_key()
        )
    
    # 检测 Continue.dev
    if is_continue_environment():
        return get_continue_llm_config()
    
    # 检测本地 LLM
    local_llm = detect_local_llm()
    if local_llm:
        return local_llm
    
    return None
```

#### 3.3 安装流程（带 LLM 配置）

```python
def add(
    skill_source: str,
    global_: bool = False,
    auto_config: bool = True,
    force: bool = False,
    use_agent_llm: bool = True,  # 🆕 使用 Agent 的 LLM
) -> None:
    """添加技能，包含 LLM 配置"""
    
    # Phase 1-4: 检测、审计、确认、安装
    # ... (现有流程)
    
    # 🆕 Phase 4.5: LLM 需求检测
    llm_requirements = detect_llm_requirements(metadata)
    
    if llm_requirements.has_requirements():
        console.print("\n[dim]Phase 4.5: Checking LLM requirements...[/dim]")
        
        # 检测 Agent 的 LLM
        agent_llm = detect_agent_llm() if use_agent_llm else None
        
        # 验证 Agent LLM 是否满足需求
        if agent_llm and llm_requirements.is_satisfied_by(agent_llm):
            console.print("[green]✓ Agent's LLM meets requirements[/green]")
            console.print(f"[dim]  Using: {agent_llm.model}[/dim]")
            
            # 自动配置使用 Agent 的 LLM
            _configure_llm_for_skill(metadata.id, agent_llm, scope)
            
        else:
            # 提示用户配置 LLM
            console.print("[yellow]⚠ LLM configuration required[/yellow]")
            console.print(f"[dim]  Required: {llm_requirements.provider}[/dim]")
            console.print(f"[dim]  Recommended: {', '.join(llm_requirements.models)}[/dim]")
            
            should_configure = questionary.confirm(
                "Configure LLM now?",
                default=True
            ).ask()
            
            if should_configure:
                _interactive_llm_configuration(metadata.id, llm_requirements, scope)
            else:
                console.print("[yellow]⚠ Skill installed but LLM not configured[/yellow]")
                console.print("[dim]  Configure later with: vibe skill configure-llm <skill-id>[/dim]")
    
    # Phase 5-6: 智能配置、验证、同步
    # ... (现有流程)
```

#### 3.4 LLM 配置向导

```python
def _interactive_llm_configuration(
    skill_id: str,
    requirements: LLMRequirements,
    scope: str
) -> None:
    """交互式 LLM 配置"""
    
    console.print(f"\n[bold cyan]🤖 LLM Configuration for {skill_id}[/bold cyan]\n")
    
    # 选择提供商
    provider = questionary.select(
        "Select LLM provider:",
        choices=[
            questionary.Choice("🤖 Anthropic (Claude)", value="anthropic"),
            questionary.Choice("🧠 OpenAI (GPT)", value="openai"),
            questionary.Choice("🔧 Local (Ollama)", value="local"),
            questionary.Choice("🔄 Other", value="other"),
        ],
        default=requirements.provider or "anthropic"
    ).ask()
    
    # 选择模型
    models = get_available_models(provider)
    model = questionary.select(
        "Select model:",
        choices=[
            questionary.Choice(
                f"{m} {'(recommended)' if m in requirements.models else ''}",
                value=m
            )
            for m in models
        ],
        default=models[0] if models else None
    ).ask()
    
    # 配置 API key
    if provider != "local":
        console.print(f"\n[dim]Configure API key for {provider}:[/dim]")
        api_key = questionary.password(
            "API key (leave empty to use env var):"
        ).ask()
        
        if not api_key:
            env_var = get_provider_env_var(provider)
            console.print(f"[dim]  Will use {env_var} environment variable[/dim]")
    
    # 参数配置
    use_defaults = questionary.confirm(
        f"Use recommended parameters? ({requirements.parameters})",
        default=True
    ).ask()
    
    parameters = requirements.parameters if use_defaults else {}
    
    # 保存配置
    llm_config = LLMConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        parameters=parameters
    )
    
    _save_llm_config(skill_id, llm_config, scope)
    
    console.print(f"\n[green]✓ LLM configured successfully[/green]")
```

---

## 📦 更新 .skill 格式

### 完整示例

```markdown
---
id: code-reviewer
name: AI Code Reviewer
description: 使用 Claude 进行智能代码审查
version: 1.0.0
author: Your Name
namespace: external
tags: [code-review, claude, quality]
skill_type: prompt

# 🆕 LLM 配置
llm_config:
  provider: anthropic
  recommended_models:
    - claude-sonnet-4-6-20250514
    - claude-3-5-sonnet-20241022
  
  min_requirements:
    context_window: 200000
    max_output: 8192
  
  default_parameters:
    temperature: 0.3
    max_tokens: 4096
  
  special_requirements:
    needs_code_context: true
    supports_thinking: true
  
  fallback_providers:
    - provider: openai
      models: [gpt-4, gpt-4-turbo]
      reason: "Claude 不可用时的备选"

# 路由配置
trigger_when: 用户需要代码审查、质量检查或最佳实践建议
priority: 75
category: review

routing_patterns:
  - .*review.*code
  - .*code.*review
  - .*check.*quality

# 依赖
dependencies:
  - pygithub >= 1.59
  - gitpython >= 3.1

env_vars:
  - GITHUB_TOKEN
  - ANTHROPIC_API_KEY
---

# AI Code Reviewer

## 技能描述

使用 Claude AI 的强大能力进行代码审查，提供质量反馈和最佳实践建议。

## LLM 需求

此技能需要：
- **提供商**: Anthropic (Claude)
- **推荐模型**: Claude Sonnet 4.6 或 Claude 3.5 Sonnet
- **上下文窗口**: 至少 200K tokens
- **输出能力**: 至少 8K tokens

## 自动配置

安装时会自动：
1. 检测 Agent 环境（Claude Code, Cursor 等）
2. 使用 Agent 自带的 Claude API
3. 如果 Agent 没有 LLM，提示用户配置

## 使用示例

### 基本代码审查

**用户**: "帮我审查这段代码"

**AI**: 使用 Claude Sonnet 4.6 进行代码审查...
---
```

---

## 🎯 用户使用流程

### 场景 1: 使用 Agent 的 LLM（推荐）

```bash
# 安装技能，自动使用 Claude Code 的 LLM
$ vibe skill add code-reviewer

Phase 4.5: Checking LLM requirements...
✓ Agent's LLM meets requirements
  Using: claude-sonnet-4-6-20250514

✨ Installation complete!

# 立即可用，无需额外配置
```

### 场景 2: 配置自定义 LLM

```bash
# 安装需要特殊 LLM 的技能
$ vibe skill add creative-writer

Phase 4.5: Checking LLM requirements...
⚠ LLM configuration required
  Required: openai
  Recommended: gpt-4

? Configure LLM now? (Y/n) Y

? Select LLM provider:
  🤖 Anthropic (Claude)
  🧠 OpenAI (GPT)        <- Selected
  🔧 Local (Ollama)
  🔄 Other

? Select model:
  gpt-4 (recommended)    <- Selected
  gpt-4-turbo

✓ LLM configured successfully
```

### 场景 3: 从不同来源安装

```bash
# 从 GitHub
vibe skill add github:user/repo/skills/code-reviewer@v1.0.0

# 从 URL
vibe skill add https://example.com/skills/custom-skill.skill

# 从本地文件
vibe skill add --source ./my-skill.skill --name custom

# 从官方仓库
vibe skill add tushare
```

---

## 🔧 实现细节

### 来源解析器

```python
class SourceResolver:
    """解析不同类型的技能来源"""
    
    def resolve(self, source: str) -> ResolvedSource:
        """解析来源并返回统一的资源对象"""
        
        source_type = detect_source_type(source)
        
        match source_type:
            case SourceType.OFFICIAL:
                return self._resolve_official(source)
            
            case SourceType.GITHUB:
                return self._resolve_github(source)
            
            case SourceType.GITLAB:
                return self._resolve_gitlab(source)
            
            case SourceType.URL:
                return self._resolve_url(source)
            
            case SourceType.LOCAL_FILE:
                return self._resolve_local_file(source)
            
            case SourceType.LOCAL_DIR:
                return self._resolve_local_dir(source)
```

### LLM 配置管理

```python
class LLMConfigManager:
    """管理技能的 LLM 配置"""
    
    def save_config(
        self,
        skill_id: str,
        config: LLMConfig,
        scope: str
    ) -> None:
        """保存 LLM 配置"""
        config_file = self._get_config_file(skill_id, scope)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        yaml.dump(
            {"llm": config.to_dict()},
            config_file
        )
    
    def get_config(
        self,
        skill_id: str,
        scope: str
    ) -> LLMConfig | None:
        """获取 LLM 配置"""
        config_file = self._get_config_file(skill_id, scope)
        
        if not config_file.exists():
            return None
        
        data = yaml.load(config_file)
        return LLMConfig.from_dict(data.get("llm", {}))
    
    def _get_config_file(
        self,
        skill_id: str,
        scope: str
    ) -> Path:
        """获取配置文件路径"""
        if scope == "global":
            return Path.home() / ".vibe" / "skills" / skill_id / "llm.yaml"
        else:
            return Path(".vibe") / "skills" / skill_id / "llm.yaml"
```

---

## 📊 配置文件示例

### 技能级别配置

```yaml
# .vibe/skills/code-reviewer/llm.yaml
llm:
  provider: anthropic
  model: claude-sonnet-4-6-20250514
  api_key_env: ANTHROPIC_API_KEY
  parameters:
    temperature: 0.3
    max_tokens: 4096
  source: agent  # 标识来源于 Agent
```

### 全局默认配置

```yaml
# .vibe/llm-defaults.yaml
defaults:
  provider: anthropic
  model: claude-sonnet-4-6-20250514
  
fallback:
  provider: openai
  model: gpt-4-turbo
  
local:
  provider: ollama
  model: llama3
```

---

## ✅ 实现清单

- [ ] 扩展 `skill_add` 命令支持多种来源
- [ ] 实现 `SourceResolver` 类
- [ ] 扩展 `SkillMetadata` 添加 `llm_config` 字段
- [ ] 实现 `detect_llm_requirements()` 函数
- [ ] 实现 `detect_agent_llm()` 函数
- [ ] 实现 LLM 配置向导
- [ ] 实现 `LLMConfigManager` 类
- [ ] 更新 .skill 格式文档
- [ ] 添加测试用例

---

## 🎁 用户体验

### 零配置体验（使用 Agent LLM）

```bash
$ vibe skill add code-reviewer
✓ Auto-detected Claude Code environment
✓ Using Claude's LLM configuration
✓ Ready to use!
```

### 灵活配置（自定义 LLM）

```bash
$ vibe skill add custom-analyzer
⚠ Requires OpenAI GPT-4
? Configure now? Yes
✓ LLM configured
```

### 多来源支持

```bash
# 官方仓库
vibe skill add tushare

# GitHub
vibe skill add github:user/skills/cool-skill

# 本地
vibe skill add ./my-skill.skill
```

---

**总结**: 这个方案提供了完整的来源指定和 LLM 自动配置功能，让技能安装更加智能和用户友好！
