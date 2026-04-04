# VibeSOP-Py v2.0 Phase 2 实施计划

> **智能关键词触发系统**
> **分支**: `feature/v2.0-keyword-triggers`
> **周期**: 2周 (12个工作日)
> **优先级**: P0 (关键功能)

---

## 📋 Phase 1 回顾

### 已完成 ✅
- WorkflowPipeline (3种执行策略)
- WorkflowManager (发现、加载、缓存)
- WorkflowStateManager (JSON 原子写入)
- CLI 工具 (list, validate, run, resume)
- 4个预定义工作流
- 114 个测试通过 (97.4%)

### 技术基础
- Pydantic v2 类型安全
- ruamel.yaml YAML 解析
- pytest 测试框架
- Typer + Rich CLI 框架

---

## 🎯 Phase 2 目标

### 核心功能
智能关键词触发系统 - 根据用户输入自动检测意图并触发相应的工作流或技能

### 用户价值
```python
# Before Phase 1
vibe workflow run security-review.yaml --input "用户输入"

# After Phase 2
vibe auto "帮我扫描安全威胁"
# 自动检测到 security 意图 → 触发 security-review 工作流
```

### 具体目标
1. ✅ **关键词检测引擎** - 准确率 > 90%
2. ✅ **30+ 预定义模式** - 覆盖常见使用场景
3. ✅ **自动技能激活** - 无缝集成现有技能系统
4. ✅ **CLI 命令** - `vibe auto <query>` 体验流畅
5. ✅ **测试覆盖** - 90%+ 覆盖率

---

## 🏗️ 技术设计

### 架构概览

```
┌─────────────────────────────────────────────────────────┐
│  User Input                                           │
│  "帮我扫描安全威胁"                                      │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  KeywordDetector (NEW Phase 2)                       │
│  - Pattern matching (TF-IDF, 规则, 语义)               │
│  - Confidence scoring (0.0 - 1.0)                      │
│  - Multi-pattern combination                            │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Trigger Patterns (NEW Phase 2)                       │
│  - 30+ 预定义模式                                      │
│  - 分类: Security, Config, Dev, Docs, Project         │
│  - 元数据: priority, confidence_threshold              │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Skill Router (Existing v1.0)                         │
│  - Semantic matching                                  │
│  - Skill discovery                                    │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  Workflow Manager (Phase 1)                            │
│  - Workflow execution                                  │
│  - State management                                   │
└─────────────────────────────────────────────────────────┘
```

### 核心组件设计

#### 1. KeywordDetector

```python
class KeywordDetector:
    """Detect user intent from natural language input.

    Uses multi-strategy matching:
    1. Rule-based patterns (regex, keywords)
    2. TF-IDF vector similarity
    3. Confidence scoring

    Attributes:
        patterns: List[TriggerPattern]
        confidence_threshold: float = 0.6

    Example:
        >>> detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        >>> match = detector.detect_best("扫描安全漏洞")
        >>> print(match.pattern_id)  # "security/scan"
        >>> print(match.confidence)  # 0.95
    """

    def detect_best(
        self,
        query: str,
        min_confidence: float = 0.6
    ) -> PatternMatch | None:
        """Detect best matching pattern for query.

        Args:
            query: User input query
            min_confidence: Minimum confidence threshold

        Returns:
            PatternMatch with pattern_id, confidence, metadata
        """
```

#### 2. Trigger Pattern Model

```python
class TriggerPattern(BaseModel):
    """A trigger pattern for automatic detection.

    Attributes:
        pattern_id: Unique identifier (e.g., "security/scan")
        name: Human-readable name
        description: What this pattern matches
        category: PatternCategory (SECURITY, CONFIG, etc.)
        keywords: List[str] - Key trigger words
        regex_patterns: List[str] - Regex patterns
        skill_id: str - Skill to activate
        workflow_id: str - Workflow to run (optional)
        priority: int - Higher priority = checked first
        confidence_threshold: float - Min confidence to match
        examples: List[str] - Example queries

    Example:
        pattern = TriggerPattern(
            pattern_id="security/scan",
            name="Security Scan",
            description="Detects security scanning requests",
            category=PatternCategory.SECURITY,
            keywords=["扫描", "scan", "检查", "安全", "漏洞"],
            regex_patterns=[
                r"扫描.*安全",
                r"安全.*检查",
                r"scan.*vulnerability"
            ],
            skill_id="/security/scan",
            workflow_id="security-review",
            priority=100,
            confidence_threshold=0.6,
            examples=[
                "扫描安全漏洞",
                "检查安全问题",
                "scan for vulnerabilities"
            ]
        )
    """
```

#### 3. Pattern Matching Algorithm

```python
def calculate_match_score(
    query: str,
    pattern: TriggerPattern
) -> float:
    """Calculate match confidence score (0.0 - 1.0).

    Strategy:
    1. Keyword matching (40%): Query contains keywords
    2. Regex matching (30%): Matches regex patterns
    3. Semantic similarity (30%): TF-IDF cosine similarity

    Returns:
        Confidence score between 0.0 and 1.0
    """
    keyword_score = _keyword_match_score(query, pattern)
    regex_score = _regex_match_score(query, pattern)
    semantic_score = _semantic_similarity_score(query, pattern)

    return (
        keyword_score * 0.4 +
        regex_score * 0.3 +
        semantic_score * 0.3
    )
```

---

## 📂 文件结构

### 新增文件

```
src/vibesop/triggers/
├── __init__.py              # Public API exports
├── models.py                # TriggerPattern, PatternMatch, PatternCategory
├── detector.py              # KeywordDetector class
├── patterns.py              # DEFAULT_PATTERNS constant (30+ patterns)
└── utils.py                 # Scoring, tokenization utilities

tests/triggers/
├── __init__.py
├── conftest.py              # Test fixtures
├── test_models.py           # Model validation tests
├── test_detector.py         # Detection logic tests
├── test_patterns.py         # Pattern library tests
├── test_scoring.py         # Scoring algorithm tests
├── integration/
│   ├── test_skill_integration.py  # Integration with SkillRouter
│   └── test_cli_integration.py      # CLI integration tests
└── e2e/
    └── test_auto_command.py        # End-to-end tests

src/vibesop/cli/commands/
└── auto.py                   # 'vibe auto' command

docs/triggers/
├── guide.md                  # User guide
└── patterns.md              # Pattern reference
```

---

## 📅 实施计划 (2周)

### Week 1: 核心功能开发

#### Day 1-2: 基础架构
**任务**:
- [ ] 创建 `src/vibesop/triggers/` 目录结构
- [ ] 实现 TriggerPattern 模型
- [ ] 实现 PatternCategory 枚举
- [ ] 创建基础测试框架

**交付物**:
- models.py (100行)
- test_models.py (15 tests)

#### Day 3-4: 关键词检测引擎
**任务**:
- [ ] 实现 KeywordDetector 类
- [ ] 关键词匹配算法
- [ ] 正则表达式匹配
- [ ] TF-IDF 相似度计算

**交付物**:
- detector.py (250行)
- utils.py (100行)
- test_detector.py (20 tests)

#### Day 5: 预定义模式库
**任务**:
- [ ] 实现 30+ 预定义模式
- [ ] 分类: Security (5), Config (5), Dev (8), Docs (6), Project (6)
- [ ] 模式验证和测试
- [ ] 模式文档

**交付物**:
- patterns.py (400行)
- test_patterns.py (15 tests)

### Week 2: 集成和优化

#### Day 6-7: 技能集成
**任务**:
- [ ] 集成 SkillRouter
- [ ] 实现自动激活逻辑
- [ ] 错误处理和降级
- [ ] 集成测试

**交付物**:
- Integration logic
- test_skill_integration.py (10 tests)

#### Day 8-9: CLI 开发
**任务**:
- [ ] 实现 `vibe auto` 命令
- [ ] Rich 输出格式化
- [ ] --dry-run 和 --verbose 选项
- [ ] CLI 集成测试

**交付物**:
- auto.py (200行)
- test_cli_integration.py (10 tests)

#### Day 10: 测试和优化
**任务**:
- [ ] 端到端测试
- [ ] 性能基准测试
- [ ] 准确率调优
- [ ] 覆盖率达到 90%+

**交付物**:
- test_auto_command.py (5 tests)
- Performance benchmarks

#### Day 11-12: 文档和收尾
**任务**:
- [ ] API 文档
- [ ] 用户指南
- [ ] 模式参考文档
- [ ] 示例代码
- [ ] 最终测试和修复

**交付物**:
- docs/triggers/guide.md
- docs/triggers/patterns.md
- examples/keyword_detection.py

---

## 🧪 测试策略

### 单元测试 (40+ tests)

#### test_models.py (15 tests)
```python
def test_trigger_pattern_validation():
    """Test pattern validation."""
    pattern = TriggerPattern(
        pattern_id="test/valid",
        name="Valid Pattern",
        keywords=["test"],
        regex_patterns=[r"test"],
        skill_id="/test",
        priority=50,
        confidence_threshold=0.5,
        examples=["test query"]
    )
    # Should validate successfully

def test_pattern_category_validation():
    """Test category validation."""
    # Test all categories
    # Test invalid categories

def test_pattern_match_model():
    """Test PatternMatch model."""
    match = PatternMatch(
        pattern_id="test/valid",
        confidence=0.85,
        metadata={}
    )
    assert match.confidence == 0.85
```

#### test_detector.py (20 tests)
```python
def test_keyword_matching():
    """Test keyword-based detection."""
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    match = detector.detect_best("扫描安全漏洞")
    assert match.pattern_id == "security/scan"
    assert match.confidence > 0.6

def test_regex_matching():
    """Test regex-based detection."""

def test_semantic_similarity():
    """Test TF-IDF similarity."""

def test_confidence_calculation():
    """Test confidence score calculation."""

def test_multi_pattern_combination():
    """Test combining multiple pattern matches."""

def test_no_match_threshold():
    """Test behavior when no pattern matches."""
```

#### test_patterns.py (15 tests)
```python
def test_security_patterns():
    """Test security category patterns."""

def test_config_patterns():
    """Test config category patterns."""

def test_development_patterns():
    """Test development category patterns."""

def test_documentation_patterns():
    """Test documentation category patterns."""

def test_project_patterns():
    """Test project management patterns."""

def test_pattern_priority():
    """Test pattern priority ordering."""
```

### 集成测试 (15+ tests)

#### test_skill_integration.py (10 tests)
```python
def test_skill_activation():
    """Test automatic skill activation."""

def test_workflow_triggering():
    """Test workflow triggering."""

def test_fallback_on_no_match():
    """Test fallback behavior."""

def test_confidence_filtering():
    """Test confidence threshold filtering."""

def test_multiple_matches_priority():
    """Test priority-based selection."""
```

#### test_cli_integration.py (5 tests)
```python
def test_auto_command_basic():
    """Test basic vibe auto command."""

def test_auto_command_dry_run():
    """Test --dry-run flag."""

def test_auto_command_verbose():
    """Test --verbose flag."""

def test_auto_command_no_match():
    """Test behavior when no pattern matches."""

def test_auto_command_low_confidence():
    """Test low confidence filtering."""
```

### E2E 测试 (5 tests)

#### test_auto_command.py (5 tests)
```python
def test_security_scan_auto_trigger():
    """Test end-to-end security scan automation."""

def test_config_deploy_auto_trigger():
    """Test end-to-end config deployment automation."""

def test_doc_generation_auto_trigger():
    """Test end-to-end doc generation automation."""

def test_complex_query_auto_trigger():
    """Test complex query with multiple intents."""

def test_fuzzy_query_auto_trigger():
    """Test fuzzy query matching."""
```

---

## 📊 成功指标

### 功能指标
- ✅ 模式准确率: >90% (30+ patterns)
- ✅ 召回率: >85% (覆盖常见场景)
- ✅ 假阳性率: <10%
- ✅ 平均响应时间: <100ms

### 质量指标
- ✅ 测试覆盖率: >90%
- ✅ 类型检查: 100% (pyright strict)
- ✅ 代码审查: 通过
- ✅ 文档完整: 100%

### 性能指标
- ✅ 检测延迟: <50ms (per query)
- ✅ 内存占用: <50MB
- ✅ 并发支持: 10+ queries/sec

---

## 🎯 关键设计决策

### 1. 多策略匹配 ⭐⭐⭐⭐⭐

**决策**: 结合关键词、正则和语义匹配

**优点**:
- 高准确率 (多策略验证)
- 健壮性强 (单一策略失败不影响)
- 可扩展 (易于添加新策略)

### 2. TF-IDF 相似度 ⭐⭐⭐⭐

**决策**: 使用 TF-IDF + 余弦相似度

**优点**:
- 无需外部依赖 (scikit-learn 太重)
- 实现简单 (~100行)
- 适合短文本

**实现**:
```python
def _tfidf_similarity(text1: str, text2: str) -> float:
    """Calculate TF-IDF cosine similarity."""
    # Tokenize
    tokens1 = _tokenize(text1)
    tokens2 = _tokenize(text2)

    # Calculate TF-IDF
    vocab = set(tokens1) | set(tokens2)
    vec1 = _tfidf_vector(tokens1, vocab)
    vec2 = _tfidf_vector(tokens2, vocab)

    # Cosine similarity
    return _cosine_similarity(vec1, vec2)
```

### 3. 优先级系统 ⭐⭐⭐⭐⭐

**决策**: 每个模式有优先级，高优先级先匹配

**优点**:
- 明确匹配顺序
- 避免歧义
- 支持覆盖

**示例**:
```python
patterns = [
    TriggerPattern(priority=100, ...),  # High priority
    TriggerPattern(priority=50, ...),   # Medium priority
    TriggerPattern(priority=10, ...),    # Low priority
]
```

### 4. 置信度阈值 ⭐⭐⭐⭐⭐

**决策**: 每个模式有置信度阈值，低于阈值不匹配

**优点**:
- 避免误触发
- 提供灵活性
- 支持调试模式

---

## ⚠️ 风险管理

### 风险 1: 准确率不达标

**概率**: 中
**影响**: 高

**缓解措施**:
1. 预定义模式由团队审核
2. 充分的测试覆盖
3. 用户反馈循环
4. 持续优化阈值

**验证**:
- 测试集: 100+ 标注查询
- 准确率 >90%

### 风险 2: 性能问题

**概率**: 低
**影响**: 中

**缓解措施**:
1. LRU 缓存常用查询
2. 异步执行 (Phase 6)
3. 性能基准测试
4. 早期性能测试

**验证**:
- <100ms 检测延迟
- 支持 10+ queries/sec

### 风险 3: 与现有系统集成

**概率**: 低
**影响**: 中

**缓解措施**:
1. 复用 Phase 1 WorkflowManager
2. 复用 v1.0 SkillRouter
3. 清晰的接口设计
4. 集成测试

**验证**:
- 所有集成测试通过
- 无回归问题

---

## 📈 开发计划时间表

### Week 1: 核心功能 (Day 1-5)

| Day | 任务 | 交付物 | 状态 |
|-----|------|--------|------|
| 1-2 | 基础架构 | models.py, test_models.py | ⏳ |
| 3-4 | 检测引擎 | detector.py, test_detector.py | ⏳ |
| 5 | 模式库 | patterns.py, test_patterns.py | ⏳ |

### Week 2: 集成优化 (Day 6-12)

| Day | 任务 | 交付物 | 状态 |
|-----|------|--------|------|
| 6-7 | 技能集成 | Integration tests | ⏳ |
| 8-9 | CLI 开发 | auto.py, CLI tests | ⏳ |
| 10 | 测试优化 | E2E tests | ⏳ |
| 11-12 | 文档收尾 | API docs, guide | ⏳ |

---

## 🚀 开始 Phase 2 开发

### 第一步: 创建分支

```bash
git checkout -b feature/v2.0-keyword-triggers
```

### 第二步: 建立目录结构

```bash
mkdir -p src/vibesop/triggers
mkdir -p tests/triggers/{integration,e2e}
mkdir -p docs/triggers
```

### 第三步: 开始实施

**Day 1 优先任务**:
1. 创建 TriggerPattern 模型
2. 实现 PatternCategory 枚举
3. 编写基础测试
4. 设置测试框架

---

**准备好开始 Phase 2!**

所有设计已完成，准备开始编码！
