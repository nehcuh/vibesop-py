# VibeSOP 技能自动理解和配置方案

## 🎯 问题理解

### 场景
```bash
# 用户在 bash 中（非 Agent 环境）
$ vibe skill add code-reviewer

# 系统需要：
# 1. 读取 code-reviewer/SKILL.md
# 2. 理解这个技能做什么
# 3. 自动配置：
#    - 优先级是多少？
#    - 路由规则是什么？
#    - 需要什么 LLM？
#    - 其他配置
```

### 核心问题
**如何在非 Agent 环境（bash）中，不使用外部 LLM，自动理解和配置技能？**

---

## 🔬 技能理解方案

### 方案对比

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|---------|
| **规则引擎** | 快速、可控、无外部依赖 | 需要预定义规则 | 常见技能类型 |
| **关键词分析** | 简单、有效 | 精度有限 | 辅助判断 |
| **分类模型** | 准确、可训练 | 需要训练数据 | 高级场景 |
| **LLM 分析** | 最智能 | 需要外部 API | 有 API key 时 |

### 推荐方案：**混合方式**

```python
# 优先级：规则引擎 > 关键词分析 > 可选 LLM
```

---

## 🏗️ 架构设计

### 核心流程

```
安装技能
    ↓
读取 SKILL.md
    ↓
解析元数据（YAML frontmatter）
    ↓
┌─────────────────────────────────┐
│   技能理解引擎 (SkillUnderstander)   │
├─────────────────────────────────┤
│ 1. 规则引擎 (RuleEngine)          │
│    - 基于 skill_type 判断          │
│    - 基于 category 判断            │
│    - 基于 tags 判断                │
├─────────────────────────────────┤
│ 2. 关键词分析器 (KeywordAnalyzer) │
│    - 从 description 提取           │
│    - 从 content 提取               │
│    - TF-IDF 相似度匹配             │
├─────────────────────────────────┤
│ 3. 分类器 (SkillClassifier)       │
│    - 预训练的分类模型              │
│    - 基于历史数据的预测            │
├─────────────────────────────────┤
│ 4. LLM 增强器 (LLMEnhancer)       │
│    - 可选的 AI 分析               │
│    - 仅在有 API key 时使用         │
└─────────────────────────────────┘
    ↓
生成配置建议
    ↓
用户确认/自动应用
```

---

## 📐 规则引擎

### 1. 基于 skill_type 的规则

```python
# src/vibesop/core/skills/understander.py

class SkillTypeRules:
    """基于技能类型的配置规则"""
    
    RULES = {
        SkillType.PROMPT: {
            "default_priority": 60,
            "requires_llm": True,
            "llm_preference": "anthropic",  # Claude 更擅长对话
            "default_temperature": 0.7,
        },
        SkillType.WORKFLOW: {
            "default_priority": 50,
            "requires_llm": False,
            "multi_step": True,
        },
        SkillType.COMMAND: {
            "default_priority": 40,
            "requires_llm": False,
            "execution_type": "shell",
        },
        SkillType.HYBRID: {
            "default_priority": 70,
            "requires_llm": True,
            "complex": True,
        },
    }
    
    @classmethod
    def get_config(cls, skill_type: SkillType) -> dict:
        """获取技能类型的默认配置"""
        return cls.RULES.get(skill_type, {})
```

### 2. 基于 category 的规则

```python
class CategoryRules:
    """基于类别的配置规则"""
    
    RULES = {
        # 开发相关
        "development": {
            "priority_range": (60, 80),
            "recommended": True,
            "llm": {
                "provider": "anthropic",
                "models": ["claude-sonnet-4-6"],
                "temperature": 0.5,
            }
        },
        
        # 调试相关
        "debugging": {
            "priority_range": (75, 95),
            "urgent": True,
            "llm": {
                "provider": "anthropic",
                "models": ["claude-sonnet-4-6"],
                "temperature": 0.3,  # 需要确定性
            }
        },
        
        # 审查相关
        "review": {
            "priority_range": (50, 70),
            "llm": {
                "provider": "anthropic",
                "models": ["claude-3-5-sonnet"],
                "temperature": 0.2,  # 非常确定性
            }
        },
        
        # 创意相关
        "brainstorming": {
            "priority_range": (40, 60),
            "llm": {
                "provider": "openai",  # GPT-4 更有创意
                "models": ["gpt-4"],
                "temperature": 0.9,  # 高创造性
            }
        },
        
        # 文档相关
        "documentation": {
            "priority_range": (30, 50),
            "llm": {
                "provider": "anthropic",
                "models": ["claude-3-haiku"],  # 快速且便宜
                "temperature": 0.5,
            }
        },
        
        # 测试相关
        "testing": {
            "priority_range": (55, 75),
            "llm": {
                "provider": "anthropic",
                "models": ["claude-sonnet-4-6"],
                "temperature": 0.4,
            }
        },
        
        # 部署相关
        "deployment": {
            "priority_range": (70, 90),
            "urgent": True,
            "llm": None,  # 可能不需要 LLM
        },
        
        # 安全相关
        "security": {
            "priority_range": (80, 100),
            "critical": True,
            "llm": {
                "provider": "anthropic",
                "models": ["claude-3-opus"],
                "temperature": 0.1,  # 极度确定性
            }
        },
    }
    
    @classmethod
    def infer_category(cls, metadata: SkillMetadata) -> str:
        """从元数据推断类别"""
        
        # 1. 从显式的 category 字段
        if hasattr(metadata, 'category') and metadata.category:
            return metadata.category
        
        # 2. 从 tags 推断
        tag_category_map = {
            "debug": "debugging",
            "test": "testing",
            "review": "review",
            "deploy": "deployment",
            "security": "security",
            "doc": "documentation",
            "brainstorm": "brainstorming",
        }
        
        if metadata.tags:
            for tag in metadata.tags:
                if tag.lower() in tag_category_map:
                    return tag_category_map[tag.lower()]
        
        # 3. 从 description 推断
        desc_lower = metadata.description.lower()
        
        category_keywords = {
            "debugging": ["debug", "error", "bug", "fix", "调试", "错误"],
            "testing": ["test", "spec", "tdd", "测试", "用例"],
            "review": ["review", "check", "quality", "审查", "检查"],
            "documentation": ["document", "doc", "readme", "文档"],
            "deployment": ["deploy", "release", "publish", "部署", "发布"],
            "security": ["security", "vulnerability", "scan", "安全", "漏洞"],
            "brainstorming": ["brainstorm", "idea", "creative", "创意", "想法"],
        }
        
        for category, keywords in category_keywords.items():
            if any(kw in desc_lower for kw in keywords):
                return category
        
        # 默认
        return "development"
```

### 3. 基于 tags 的规则

```python
class TagRules:
    """基于标签的配置规则"""
    
    # 特殊标签的配置
    SPECIAL_TAGS = {
        "urgent": {
            "priority_boost": 20,
        },
        "experimental": {
            "priority_penalty": 10,
            "enabled_default": False,
        },
        "deprecated": {
            "enabled_default": False,
        },
        "requires-claude": {
            "llm_provider": "anthropic",
        },
        "requires-gpt4": {
            "llm_provider": "openai",
            "min_model": "gpt-4",
        },
    }
    
    @classmethod
    def apply_tag_rules(cls, metadata: SkillMetadata, base_config: dict) -> dict:
        """应用标签规则"""
        
        config = base_config.copy()
        
        if not metadata.tags:
            return config
        
        for tag in metadata.tags:
            tag_lower = tag.lower()
            
            if tag_lower in cls.SPECIAL_TAGS:
                rule = cls.SPECIAL_TAGS[tag_lower]
                config.update(rule)
        
        return config
```

---

## 🔍 关键词分析器

### 1. 关键词提取增强

```python
class KeywordAnalyzer:
    """增强的关键词分析器"""
    
    # 类别关键词库
    CATEGORY_KEYWORDS = {
        "debugging": [
            "debug", "error", "bug", "fix", "troubleshoot", "diagnose",
            "调试", "错误", "故障", "修复", "诊断"
        ],
        "testing": [
            "test", "spec", "tdd", "verify", "check",
            "测试", "验证", "检查", "用例"
        ],
        "review": [
            "review", "audit", "quality", "inspect", "analyze",
            "审查", "审计", "质量", "分析"
        ],
        "documentation": [
            "document", "doc", "readme", "guide", "tutorial",
            "文档", "指南", "教程"
        ],
        "deployment": [
            "deploy", "release", "publish", "ship", "ci/cd",
            "部署", "发布", "上线"
        ],
        "security": [
            "security", "vulnerability", "scan", "audit",
            "安全", "漏洞", "扫描"
        ],
        "brainstorming": [
            "brainstorm", "idea", "creative", "innovate",
            "头脑风暴", "创意", "创新"
        ],
        "optimization": [
            "optimize", "performance", "improve", "speed",
            "优化", "性能", "改进"
        ],
    }
    
    # LLM 需求关键词
    LLM_KEYWORDS = [
        "ai", "llm", "gpt", "claude", "anthropic", "openai",
        "分析", "生成", "理解", "总结", "解释"
    ]
    
    # 复杂度关键词
    COMPLEXITY_KEYWORDS = {
        "high": ["complex", "architecture", "system", "multi", "复杂", "架构"],
        "medium": ["module", "component", "feature", "模块", "组件"],
        "low": ["simple", "basic", "quick", "简单", "基础"],
    }
    
    @classmethod
    def analyze(cls, text: str) -> dict:
        """分析文本，提取特征"""
        
        analysis = {
            "categories": [],
            "requires_llm": False,
            "complexity": "medium",
            "urgency": "normal",
            "keywords": [],
        }
        
        text_lower = text.lower()
        
        # 1. 类别检测
        for category, keywords in cls.CATEGORY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                analysis["categories"].append(category)
        
        # 2. LLM 需求检测
        if any(kw in text_lower for kw in cls.LLM_KEYWORDS):
            analysis["requires_llm"] = True
        
        # 3. 复杂度检测
        for complexity, keywords in cls.COMPLEXITY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                analysis["complexity"] = complexity
                break
        
        # 4. 紧急性检测
        urgency_keywords = ["urgent", "critical", "important", "紧急", "重要"]
        if any(kw in text_lower for kw in urgency_keywords):
            analysis["urgency"] = "high"
        
        # 5. 提取主要关键词
        analysis["keywords"] = cls._extract_keywords(text)
        
        return analysis
    
    @classmethod
    def _extract_keywords(cls, text: str) -> list[str]:
        """提取关键词（改进版）"""
        
        import re
        from collections import Counter
        
        # 提取单词
        words = re.findall(r"\b\w{3,}\b", text.lower())
        
        # 过滤停用词
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "can", "need", "for", "with", "from", "this", "that", "use",
            "用户", "帮助", "使用", "需要", "可以"
        }
        
        keywords = [w for w in words if w not in stop_words]
        
        # 返回最常见的 5 个
        counter = Counter(keywords)
        return [word for word, _ in counter.most_common(5)]
```

### 2. TF-IDF 相似度匹配

```python
class SkillSimilarityMatcher:
    """基于 TF-IDF 的技能相似度匹配"""
    
    # 预定义的技能模板
    SKILL_TEMPLATES = {
        "systematic-debugging": {
            "description": "Systematic debugging workflow",
            "keywords": ["debug", "error", "systematic", "workflow"],
            "category": "debugging",
            "priority": 80,
        },
        "code-review": {
            "description": "Code review and quality check",
            "keywords": ["review", "code", "quality", "check"],
            "category": "review",
            "priority": 60,
        },
        "test-generation": {
            "description": "Generate test cases",
            "keywords": ["test", "generate", "tdd", "spec"],
            "category": "testing",
            "priority": 65,
        },
        # ... 更多模板
    }
    
    @classmethod
    def find_most_similar(cls, metadata: SkillMetadata) -> dict:
        """找到最相似的技能模板"""
        
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        
        # 准备文本
        skill_text = f"{metadata.name} {metadata.description}"
        
        # 计算相似度
        templates_text = [
            f"{tpl['description']} {' '.join(tpl['keywords'])}"
            for tpl in cls.SKILL_TEMPLATES.values()
        ]
        
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform([skill_text] + templates_text)
        
        similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
        
        # 找到最相似的
        max_idx = similarities.argmax()
        most_similar = list(cls.SKILL_TEMPLATES.values())[max_idx]
        
        return {
            "template_name": list(cls.SKILL_TEMPLATES.keys())[max_idx],
            "similarity": float(similarities[max_idx]),
            "suggested_config": most_similar,
        }
```

---

## 🤖 自动配置生成器

### 配置生成流程

```python
class SkillAutoConfigurator:
    """技能自动配置生成器"""
    
    def generate_config(
        self,
        metadata: SkillMetadata,
        skill_content: str
    ) -> AutoGeneratedConfig:
        """生成自动配置"""
        
        # Step 1: 分析技能
        analysis = self._analyze_skill(metadata, skill_content)
        
        # Step 2: 应用规则引擎
        rule_config = self._apply_rules(metadata, analysis)
        
        # Step 3: 关键词分析
        keyword_config = self._apply_keywords(metadata, skill_content)
        
        # Step 4: 相似度匹配
        similarity_config = self._apply_similarity(metadata)
        
        # Step 5: 合并配置（按优先级）
        final_config = self._merge_configs(
            rule_config,
            keyword_config,
            similarity_config
        )
        
        # Step 6: 可选：LLM 增强（如果可用）
        if self._has_llm_access():
            llm_enhanced = self._llm_enhance(metadata, final_config)
            final_config = self._merge_configs(final_config, llm_enhanced)
        
        return final_config
    
    def _analyze_skill(
        self,
        metadata: SkillMetadata,
        content: str
    ) -> SkillAnalysis:
        """分析技能特征"""
        
        analysis = SkillAnalysis()
        
        # 基础信息
        analysis.skill_type = metadata.skill_type
        analysis.tags = metadata.tags or []
        
        # 关键词分析
        keyword_analysis = KeywordAnalyzer.analyze(
            f"{metadata.name} {metadata.description} {content}"
        )
        analysis.categories = keyword_analysis["categories"]
        analysis.requires_llm = keyword_analysis["requires_llm"]
        analysis.complexity = keyword_analysis["complexity"]
        analysis.urgency = keyword_analysis["urgency"]
        
        # 推断类别
        if not analysis.categories:
            analysis.categories.append(
                CategoryRules.infer_category(metadata)
            )
        
        return analysis
    
    def _apply_rules(
        self,
        metadata: SkillMetadata,
        analysis: SkillAnalysis
    ) -> dict:
        """应用规则引擎"""
        
        config = {}
        
        # 1. 技能类型规则
        type_config = SkillTypeRules.get_config(metadata.skill_type)
        config.update(type_config)
        
        # 2. 类别规则
        primary_category = analysis.categories[0] if analysis.categories else "development"
        category_config = CategoryRules.RULES.get(primary_category, {})
        config.update(category_config)
        
        # 3. 标签规则
        config = TagRules.apply_tag_rules(metadata, config)
        
        # 4. 复杂度调整
        if analysis.complexity == "high":
            config["priority"] = config.get("priority", 50) + 10
        elif analysis.complexity == "low":
            config["priority"] = config.get("priority", 50) - 5
        
        # 5. 紧急性调整
        if analysis.urgency == "high":
            config["priority"] = config.get("priority", 50) + 15
        
        return config
    
    def _apply_keywords(
        self,
        metadata: SkillMetadata,
        content: str
    ) -> dict:
        """应用关键词分析"""
        
        keyword_analysis = KeywordAnalyzer.analyze(
            f"{metadata.name} {metadata.description} {content}"
        )
        
        config = {}
        
        # 如果分析出需要 LLM
        if keyword_analysis["requires_llm"]:
            config["requires_llm"] = True
            
            # 根据类别选择 LLM
            primary_category = keyword_analysis["categories"][0] if keyword_analysis["categories"] else "development"
            
            if primary_category in CategoryRules.RULES:
                category_rule = CategoryRules.RULES[primary_category]
                if "llm" in category_rule:
                    config["llm_config"] = category_rule["llm"]
        
        # 生成路由模式
        keywords = keyword_analysis["keywords"]
        if keywords:
            config["routing_patterns"] = [
                f".*{kw}.*" for kw in keywords[:5]
            ]
        
        return config
    
    def _apply_similarity(self, metadata: SkillMetadata) -> dict:
        """应用相似度匹配"""
        
        similar = SkillSimilarityMatcher.find_most_similar(metadata)
        
        config = {}
        
        # 如果相似度高，使用模板配置
        if similar["similarity"] > 0.7:
            template_config = similar["suggested_config"]
            
            config["category"] = template_config["category"]
            config["priority"] = template_config["priority"]
            
            # 标记来源
            config["config_source"] = f"similarity_match:{similar['template_name']}"
            config["similarity_score"] = similar["similarity"]
        
        return config
    
    def _merge_configs(self, *configs) -> dict:
        """合并多个配置（后面的覆盖前面的）"""
        
        merged = {}
        
        # 定义优先级
        priority_order = [
            "rule_engine",      # 最低优先级
            "keyword_analysis", # 中等优先级
            "similarity_match", # 较高优先级
            "llm_enhanced",     # 最高优先级
        ]
        
        # 按优先级合并
        for config in configs:
            # 确定配置来源
            source = config.get("config_source", "unknown")
            
            # 特殊字段优先级处理
            for key, value in config.items():
                if key == "priority":
                    # 优先级累加（有上限）
                    current = merged.get("priority", 50)
                    if isinstance(value, int):
                        merged["priority"] = min(100, current + value * 0.3)
                elif key not in merged:
                    merged[key] = value
        
        # 确保优先级在合理范围
        if "priority" in merged:
            merged["priority"] = max(0, min(100, int(merged["priority"])))
        
        return merged
    
    def _has_llm_access(self) -> bool:
        """检查是否有 LLM 访问权限"""
        
        import os
        
        # 检查环境变量
        if os.getenv("ANTHROPIC_API_KEY"):
            return True
        
        if os.getenv("OPENAI_API_KEY"):
            return True
        
        # 检查配置文件
        config_file = Path.home() / ".vibe" / "config.yaml"
        if config_file.exists():
            import yaml
            with open(config_file) as f:
                config = yaml.safe_load(f)
                if config.get("llm", {}).get("api_key"):
                    return True
        
        return False
    
    def _llm_enhance(
        self,
        metadata: SkillMetadata,
        current_config: dict
    ) -> dict:
        """使用 LLM 增强配置（可选）"""
        
        try:
            enhancer = AIEnhancer()
            
            # 创建建议对象
            suggestion = SkillSuggestion(
                skill_name=metadata.name,
                skill_id=metadata.id,
                description=metadata.description,
                frequency=1,
                trigger_queries=[metadata.description],
                examples=[],
                suggested_category=current_config.get("category", "development"),
            )
            
            enhanced = enhancer.enhance_suggestion(suggestion)
            
            # 转换为配置格式
            config = {
                "category": enhanced.category,
                "tags": enhanced.tags,
                "priority": self._calculate_priority_from_category(enhanced.category),
                "config_source": "llm_enhanced",
                "llm_config": self._suggest_llm_for_category(enhanced.category),
            }
            
            return config
            
        except Exception as e:
            # LLM 调用失败，返回空配置
            return {}
    
    def _calculate_priority_from_category(self, category: str) -> int:
        """根据类别计算优先级"""
        
        category_priority = {
            "security": 90,
            "deployment": 80,
            "debugging": 75,
            "testing": 65,
            "development": 60,
            "review": 55,
            "optimization": 55,
            "brainstorming": 45,
            "documentation": 40,
        }
        
        return category_priority.get(category, 50)
    
    def _suggest_llm_for_category(self, category: str) -> dict:
        """为类别建议 LLM 配置"""
        
        llm_suggestions = {
            "debugging": {
                "provider": "anthropic",
                "models": ["claude-sonnet-4-6"],
                "temperature": 0.3,
            },
            "review": {
                "provider": "anthropic",
                "models": ["claude-3-5-sonnet"],
                "temperature": 0.2,
            },
            "brainstorming": {
                "provider": "openai",
                "models": ["gpt-4"],
                "temperature": 0.9,
            },
            "development": {
                "provider": "anthropic",
                "models": ["claude-sonnet-4-6"],
                "temperature": 0.5,
            },
        }
        
        return llm_suggestions.get(category, {})
```

---

## 🎯 完整安装流程（更新）

```python
def add(
    skill_source: str,
    global_: bool = False,
    auto_config: bool = True,
    force: bool = False,
    enable_llm: bool = False,  # 🆕 是否启用 LLM 增强
) -> None:
    """添加技能，包含自动理解和配置"""
    
    # Phase 1-4: 检测、审计、确认、安装
    # ... (现有流程)
    
    # 🆕 Phase 5: 自动理解和配置
    if auto_config:
        console.print("\n[dim]Phase 5: Understanding skill and generating config...[/dim]")
        
        # 读取技能内容
        skill_content = _read_skill_content(install_result["installed_path"])
        
        # 自动配置生成器
        configurator = SkillAutoConfigurator()
        
        # 生成配置
        auto_config = configurator.generate_config(
            metadata,
            skill_content
        )
        
        # 显示理解结果
        console.print(f"[dim]  Understood as:[/dim] {auto_config.get('category', 'development')}")
        console.print(f"[dim]  Priority:[/dim] {auto_config.get('priority', 50)}")
        
        if auto_config.get("requires_llm"):
            llm_cfg = auto_config.get("llm_config", {})
            console.print(f"[dim]  LLM Provider:[/dim] {llm_cfg.get('provider', 'anthropic')}")
            console.print(f"[dim]  Model:[/dim] {llm_cfg.get('models', ['claude-sonnet-4-6'])[0]}")
        
        # 保存配置
        _save_auto_config(auto_config)
        
        # LLM 配置检查
        if auto_config.get("requires_llm"):
            console.print("\n[dim]Phase 5.5: LLM configuration check...[/dim]")
            
            # 检查用户是否已配置 LLM
            has_llm = _check_llm_config()
            
            if not has_llm:
                llm_cfg = auto_config.get("llm_config", {})
                
                console.print("[yellow]⚠ This skill requires LLM configuration[/yellow]")
                console.print(f"[dim]  Recommended: {llm_cfg.get('provider')} {llm_cfg.get('models', [''])[0]}[/dim]")
                
                should_config = questionary.confirm(
                    "Configure LLM now?",
                    default=True
                ).ask()
                
                if should_config:
                    _configure_llm(interactive=True)
                else:
                    console.print("[dim]  Configure later with: vibe config llm[/dim]")
            else:
                console.print("[green]✓ LLM already configured[/green]")
    
    # Phase 6: 验证和同步
    # ... (现有流程)
```

---

## 📊 配置示例

### 示例 1: 调试技能

```bash
$ vibe skill add systematic-debugging

Phase 5: Understanding skill and generating config...
  Analyzed: debugging (confidence: 0.92)
  Priority: 85 (high urgency)
  LLM: Not required

✓ Config auto-generated
```

生成的配置：
```yaml
# .vibe/skills/auto-config.yaml
systematic-debugging:
  category: debugging
  priority: 85
  requires_llm: false
  routing_patterns:
    - .*debug.*
    - .*error.*
    - .*bug.*
  config_source: rule_engine+keyword_analysis
```

### 示例 2: 代码审查技能

```bash
$ vibe skill add code-reviewer

Phase 5: Understanding skill and generating config...
  Analyzed: review (confidence: 0.89)
  Priority: 60
  LLM Provider: anthropic
  Model: claude-3-5-sonnet
  Temperature: 0.2

Phase 5.5: LLM configuration check...
✓ LLM already configured (Claude Code)

✓ Config auto-generated
```

生成的配置：
```yaml
code-reviewer:
  category: review
  priority: 60
  requires_llm: true
  llm_config:
    provider: anthropic
    models: [claude-3-5-sonnet]
    temperature: 0.2
  routing_patterns:
    - .*review.*
    - .*code.*check
  config_source: rule_engine+similarity_match
```

---

## ✅ 实现优先级

### Phase 1: 核心理解引擎 (P0)

- [x] 规则引擎（SkillTypeRules, CategoryRules, TagRules）
- [x] 关键词分析器（KeywordAnalyzer）
- [ ] 配置生成器（SkillAutoConfigurator）

### Phase 2: LLM 集成 (P1)

- [ ] LLM 需求检测
- [ ] LLM 配置向导
- [ ] Agent 环境检测

### Phase 3: 高级功能 (P2)

- [ ] TF-IDF 相似度匹配
- [ ] 机器学习分类器
- [ ] 配置学习和优化

---

## 🎁 用户体验

### 自动理解

```bash
$ vibe skill add my-custom-skill

Phase 5: Understanding skill...
  📊 Analyzing skill description...
  🎯 Category: development (matched keywords: develop, code)
  ⚡ Priority: 65 (based on category + complexity)
  🤖 LLM: anthropic/claude-sonnet (recommended for development)
  📝 Routing: 3 patterns generated

✓ Auto-configured and ready to use!
```

### 配置预览

```bash
$ vibe skill add code-analyzer --show-config

Phase 5: Understanding skill...
  📊 Config Preview:
     
     Category: review
     Priority: 70
     LLM: claude-3-5-sonnet (0.2 temp)
     Routes: .*review.*code, .*code.*quality
     
? Apply this config? (Y/n) Y

✓ Config applied
```

---

**总结**: 这个方案提供了**不依赖 Agent 的技能理解和自动配置能力**，通过规则引擎、关键词分析和可选的 LLM 增强来实现智能配置！
