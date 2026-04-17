# VibeSOP Intelligent Trigger System - User Guide

> **Version**: 2.0.0
> **Last Updated**: 2026-04-04
> **Phase**: 2 - Intelligent Keyword Trigger System

---

> ⚠️ **DEPRECATION NOTICE**
>
> The `vibe auto` command documented in this guide was **removed in v4.1.0**.
> VibeSOP is now a pure routing engine. Use `vibe route <query>` instead.
> This document is kept for historical reference only.

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [How It Works](#how-it-works)
4. [Using the CLI](#using-the-cli)
5. [Using the API](#using-the-api)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Usage](#advanced-usage)

---

## Overview

The VibeSOP Intelligent Trigger System automatically detects user intent from natural language queries and activates appropriate skills or workflows. It supports both English and Chinese queries with high accuracy.

### Key Features

- **🎯 Automatic Intent Detection**: 30+ predefined patterns covering common development tasks
- **🌍 Bilingual Support**: Works with both English and Chinese queries
- **⚡ Fast Performance**: Detects intent in < 3ms (427 queries/second)
- **🔄 Fallback Routing**: Seamlessly falls back to semantic routing if needed
- **🛠️ Easy Integration**: Simple CLI and Python API

### Supported Categories

| Category | Description | Example Queries |
|----------|-------------|-----------------|
| 🔒 **Security** | Security scanning, analysis, auditing | "scan for vulnerabilities", "安全审计" |
| ⚙️ **Config** | Configuration deployment, validation | "deploy config", "验证配置" |
| 🛠️ **Dev** | Build, test, debug, refactor | "run tests", "调试错误" |
| 📚 **Docs** | Documentation generation, formatting | "generate docs", "生成文档" |
| 📁 **Project** | Project initialization, migration | "init project", "项目迁移" |

---

## Quick Start

### Installation

The trigger system is included in VibeSOP-Py v2.0+. Install with:

```bash
pip install vibesop
# or
uv pip install vibesop
```

### Basic Usage

#### 1. Using the CLI (Easiest)

```bash
# Detect and execute automatically
vibe auto "scan for security vulnerabilities"

# Preview what would happen (dry-run)
vibe auto --dry-run "deploy configuration to production"

# Adjust confidence threshold
vibe auto --min-confidence 0.5 "test code"

# Provide input data
vibe auto "scan" --input '{"target": "./src"}'
```

#### 2. Using the Python API

```python
import asyncio
from vibesop.triggers import KeywordDetector, SkillActivator, DEFAULT_PATTERNS

# Detect intent
detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
match = detector.detect_best("scan for security issues")

if match:
    print(f"Detected: {match.pattern_id} (confidence: {match.confidence:.2%})")

    # Activate skill/workflow
    activator = SkillActivator()
    result = asyncio.run(activator.activate(match))

    if result["success"]:
        print("Execution successful!")
else:
    print("No intent detected")
```

---

## How It Works

### Detection Pipeline

```
User Query
     ↓
[1] Tokenization
     ├─ English: word-based tokens
     └─ Chinese: 2-char + 1-char tokens
     ↓
[2] Pattern Matching (3 strategies)
     ├─ Keywords (40%): Exact/partial word matches
     ├─ Regex (30%): Pattern-based matches
     └─ Semantic (30%): TF-IDF similarity
     ↓
[3] Scoring & Ranking
     ├─ Combine scores from all strategies
     ├─ Apply pattern priority
     └─ Filter by confidence threshold
     ↓
[4] Result
     ├─ Best match (if confidence ≥ threshold)
     └─ No match (if confidence < threshold)
```

### Multi-Strategy Scoring

The system uses a lenient scoring algorithm where the first match gives 0.5 baseline, making pattern matching more effective:

```
Score = 0.5 (first match) + (additional_matches - 1) * 0.5 / total_items
```

**Example**: For a pattern with 6 keywords:
- 1 match → 0.5 score
- 2 matches → 0.58 score
- 3 matches → 0.67 score

### Confidence Thresholds

- **Default**: 0.6 (60%)
- **Recommended range**: 0.4 - 0.7
- **Lower (0.4)**: More matches, some false positives
- **Higher (0.7)**: Fewer matches, more precision

### Pattern Priority

Patterns with higher `priority` (1-100) are checked first:

```
Priority 100: Security scan, Config deploy (most common)
Priority 95-90: Important workflows
Priority 80-70: Standard operations
Priority 60-50: Utility operations
```

---

## Using the CLI

### The `vibe auto` Command

```bash
vibe auto [OPTIONS] QUERY
```

#### Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--input` | `-i` | None | Input data as JSON string |
| `--min-confidence` | `-c` | 0.6 | Minimum confidence threshold (0.0-1.0) |
| `--dry-run` | | False | Show what would happen without executing |
| `--verbose` | `-v` | False | Show detailed detection information |

### Examples

#### Basic Usage

```bash
# Detect and execute
vibe auto "scan for security vulnerabilities"
```

**Output**:
```
🎯 Intelligent Auto-Execution
========================================

Query: scan for security vulnerabilities

Detecting intent (min confidence: 0.60)...

╭─────────────────────────────────────────╮
│ ✓ Intent Detected                      │
│                                         │
│ [🔒] Security Scan                     │
│                                         │
│ ID: security/scan                       │
│ Category: security                      │
│ Confidence: 85%                         │
│ Description: Detects security scanning  │
│   and vulnerability detection requests  │
│                                         │
│ Keywords: scan, security                │
╰─────────────────────────────────────────╯

Executing...
```

#### Dry Run Mode

```bash
vibe auto --dry-run "deploy configuration to production"
```

**Output**:
```
╭─────────────────────────────────────────╮
│ 🔍 DRY RUN                              │
│                                         │
│ Action: WORKFLOW                         │
│ Pattern: Config Deploy                  │
│ Description: Detects configuration...   │
│                                         │
│ Will execute:                           │
│   • Workflow: config-deploy             │
│   • Query: Detects configuration...     │
│                                         │
│ Remove --dry-run to execute.            │
╰─────────────────────────────────────────╯
```

#### With Input Data

```bash
vibe auto "scan" --input '{"target": "./src", "severity": "high"}'
```

#### Custom Confidence Threshold

```bash
# More permissive (more matches)
vibe auto --min-confidence 0.4 "test code"

# More strict (fewer matches)
vibe auto --min-confidence 0.7 "security audit"
```

#### Verbose Mode

```bash
vibe auto --verbose "generate documentation"
```

Shows:
- Matched keywords
- Regex patterns matched
- Semantic similarity score
- Skill/Workflow IDs

### Chinese Queries

```bash
# Chinese queries work seamlessly
vibe auto "扫描安全漏洞"
vibe auto "部署配置到生产环境"
vibe auto "运行测试"
```

### Mixed Language

```bash
# Mix English and Chinese
vibe auto "帮我 scan security issues"
```

---

## Using the API

### 1. Keyword Detection

```python
from vibesop.triggers import KeywordDetector, DEFAULT_PATTERNS

# Create detector
detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

# Detect best match
match = detector.detect_best("scan for security vulnerabilities")

if match:
    print(f"Pattern: {match.pattern_id}")
    print(f"Confidence: {match.confidence:.2%}")
    print(f"Category: {match.metadata['category']}")
    print(f"Matched keywords: {match.matched_keywords}")
    print(f"Matched regex: {match.matched_regex}")
    print(f"Semantic score: {match.semantic_score}")
else:
    print("No match found")
```

### 2. Custom Confidence Threshold

```python
# Lower threshold for more matches
match = detector.detect_best("test", min_confidence=0.4)

# Higher threshold for fewer matches
match = detector.detect_best("security audit", min_confidence=0.7)
```

### 3. Get All Matches

```python
# Get all matches above threshold
matches = detector.detect_all("scan security", min_confidence=0.5)

for i, match in enumerate(matches, 1):
    print(f"{i}. {match.pattern_id}: {match.confidence:.2%}")
```

### 4. Skill Activation

```python
import asyncio
from vibesop.triggers import SkillActivator

async def execute_with_detection():
    # Detect intent
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    match = detector.detect_best("scan for security issues")

    if not match:
        print("No intent detected")
        return

    # Activate skill/workflow
    activator = SkillActivator()
    result = await activator.activate(
        match,
        input_data={"target": "./src"}
    )

    if result["success"]:
        action = result["action"]  # "skill" or "workflow"
        print(f"{action.title()} executed successfully!")

        if action == "skill":
            print(f"Skill ID: {result.get('skill_id')}")
        elif action == "workflow":
            print(f"Workflow ID: {result.get('workflow_id')}")
    else:
        print(f"Execution failed: {result.get('error')}")

# Run
asyncio.run(execute_with_detection())
```

### 5. Custom Patterns

```python
from vibesop.triggers.models import TriggerPattern, PatternCategory

# Create custom pattern
custom_pattern = TriggerPattern(
    pattern_id="custom/deploy",
    name="Custom Deploy",
    description="Deploy to custom environment",
    category=PatternCategory.CONFIG,
    keywords=["deploy", "publish", "release"],
    regex_patterns=[r"deploy.*production", r"publish.*release"],
    skill_id="/custom/deploy-skill",
    priority=95,
    confidence_threshold=0.6,
    examples=["deploy to production", "publish release"]
)

# Use with detector
detector = KeywordDetector(patterns=[custom_pattern])
match = detector.detect_best("deploy to production")
```

### 6. Convenience Function

```python
import asyncio
from vibesop.triggers import auto_activate

# One-shot detection and activation
result = asyncio.run(
    auto_activate(
        query="scan for security issues",
        project_root=".",  # Current directory
        min_confidence=0.6,
        input_data={"target": "./src"}
    )
)

if result["success"]:
    print("Success!")
else:
    print(f"Failed: {result.get('error')}")
```

---

## Best Practices

### 1. Query Formulation

**✅ DO:**
- Use clear, specific keywords: "scan for security vulnerabilities"
- Include context: "run unit tests for src/"
- Use complete phrases: "generate API documentation"

**❌ DON'T:**
- Use vague queries: "test" (too generic)
- Use single words: "scan" (ambiguous)
- Use typos: "genarate docs" (reduces accuracy)

### 2. Confidence Thresholds

```python
# For permissive matching (more results, potential false positives)
min_confidence=0.4

# For balanced matching (recommended default)
min_confidence=0.6

# For strict matching (fewer results, high precision)
min_confidence=0.7
```

### 3. Input Data

```python
# Provide structured input for better execution
input_data = {
    "target": "./src",
    "severity": "high",
    "output_format": "json"
}
```

### 4. Error Handling

```python
import asyncio
from vibesop.triggers import KeywordDetector, SkillActivator

async def safe_execute(query: str):
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    match = detector.detect_best(query)

    if not match:
        print("❌ No intent detected")
        print("💡 Try rephrasing your query")
        return False

    try:
        activator = SkillActivator()
        result = await activator.activate(match)

        if result["success"]:
            print("✅ Execution successful")
            return True
        else:
            print(f"❌ Execution failed: {result.get('error')}")
            return False

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

# Usage
asyncio.run(safe_execute("scan for security issues"))
```

### 5. Performance Optimization

```python
# Reuse detector instance (expensive to create)
detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

# Batch processing
queries = ["scan security", "deploy config", "run tests"]
for query in queries:
    match = detector.detect_best(query)
    # Process match...
```

---

## Troubleshooting

### Problem: "No intent detected"

**Causes:**
1. Query too vague or generic
2. Confidence threshold too high
3. Query doesn't match any patterns

**Solutions:**

```bash
# 1. Lower confidence threshold
vibe auto --min-confidence 0.4 "your query"

# 2. Use more specific keywords
vibe auto "scan for security vulnerabilities in my code"

# 3. Use verbose mode to see why
vibe auto --verbose "your query"
```

### Problem: Wrong intent detected

**Causes:**
1. Ambiguous query
2. Multiple patterns match
3. Keywords overlap between patterns

**Solutions:**

```python
# 1. Check all matches (not just best)
detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
matches = detector.detect_all("your query", min_confidence=0.4)
for match in matches:
    print(f"{match.pattern_id}: {match.confidence:.2%}")

# 2. Use more specific language
"scan for SECURITY vulnerabilities"  # Emphasize key words

# 3. Use skill/workflow directly instead
```

### Problem: Low confidence scores

**Causes:**
1. Query doesn't use pattern keywords
2. Query is too short
3. Typos in query

**Solutions:**

```python
# 1. Use pattern keywords
# Instead of: "check for threats"
# Use: "scan for security vulnerabilities"

# 2. Provide more context
# Instead of: "scan"
# Use: "scan for security vulnerabilities in my code"

# 3. Check spelling
# "generate docs" ✅
# "genarate docs" ❌
```

### Problem: Execution fails

**Causes:**
1. Skill/workflow not found
2. Invalid input data
3. Missing permissions

**Solutions:**

```python
# 1. Check if skill/workflow exists
vibe skills  # List available skills
vibe workflow list  # List available workflows

# 2. Validate input data
import json
input_data = json.loads('{"target": "./src"}')

# 3. Use verbose mode
vibe auto --verbose "your query"
```

---

## Advanced Usage

### 1. Custom Pattern Libraries

```python
from vibesop.triggers import KeywordDetector, DEFAULT_PATTERNS
from vibesop.triggers.models import TriggerPattern, PatternCategory

# Define custom patterns
MY_PATTERNS = [
    TriggerPattern(
        pattern_id="myapp/deploy",
        name="MyApp Deploy",
        description="Deploy MyApp to production",
        category=PatternCategory.CONFIG,
        keywords=["deploy", "myapp", "production"],
        skill_id="/myapp/deploy",
        priority=100
    ),
    # ... more patterns
]

# Combine with defaults
ALL_PATTERNS = DEFAULT_PATTERNS + MY_PATTERNS

# Use combined detector
detector = KeywordDetector(patterns=ALL_PATTERNS)
```

### 2. Async Batch Processing

```python
import asyncio
from vibesop.triggers import KeywordDetector, SkillActivator

async def process_batch(queries: list[str]):
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    activator = SkillActivator()

    tasks = []
    for query in queries:
        match = detector.detect_best(query)
        if match:
            tasks.append(activator.activate(match))

    results = await asyncio.gather(*tasks)
    return results

# Usage
queries = [
    "scan for security issues",
    "deploy configuration",
    "run tests"
]
results = asyncio.run(process_batch(queries))
```

### 3. Integration with Routing

```python
from vibesop.triggers import KeywordDetector
from vibesop.core.routing.engine import SkillRouter
from vibesop.triggers import SkillActivator

async def intelligent_routing(query: str):
    # Try keyword detection first
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    match = detector.detect_best(query)

    if match and match.confidence >= 0.8:
        # High confidence: use direct activation
        activator = SkillActivator()
        return await activator.activate(match)
    else:
        # Low confidence: fall back to semantic routing
        router = SkillRouter()
        route = router.route(query)
        # Execute routed skill...
```

### 4. Pattern Analysis

```python
from vibesop.triggers import KeywordDetector, DEFAULT_PATTERNS

def analyze_pattern_coverage():
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

    test_queries = [
        "scan security",
        "deploy config",
        "run tests",
        # ... more queries
    ]

    coverage = {}
    for query in test_queries:
        match = detector.detect_best(query)
        if match:
            coverage[query] = {
                "pattern": match.pattern_id,
                "confidence": match.confidence,
                "category": match.metadata["category"]
            }
        else:
            coverage[query] = None

    return coverage

# Analyze which patterns are most effective
coverage = analyze_pattern_coverage()
```

### 5. Performance Monitoring

```python
import time
from vibesop.triggers import KeywordDetector

def benchmark_detection(queries: list[str]):
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

    start = time.time()
    for query in queries:
        detector.detect_best(query)
    elapsed = time.time() - start

    avg_time = elapsed / len(queries)
    qps = len(queries) / elapsed

    print(f"Average: {avg_time * 1000:.2f}ms per query")
    print(f"Throughput: {qps:.0f} queries/second")

# Benchmark
queries = ["test"] * 1000
benchmark_detection(queries)
```

---

## Next Steps

- **Pattern Reference**: See [pattern reference docs](./patterns.md) for complete pattern list
- **API Documentation**: See [API docs](./api.md) for detailed API reference
- **Examples**: Check `/examples` directory for code examples
- **Contributing**: See [contributing guide](../../CONTRIBUTING.md) to add new patterns

---

## Support

- **Issues**: https://github.com/nehcuh/vibesop-py/issues
- **Discussions**: https://github.com/nehcuh/vibesop-py/discussions
- **Documentation**: https://vibesop.readthedocs.io/

---

*Last updated: 2026-04-04*
