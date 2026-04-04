# VibeSOP Trigger System - API Documentation

> **Version**: 2.0.0
> **Last Updated**: 2026-04-04

---

## Table of Contents

1. [Core Models](#core-models)
2. [Detector API](#detector-api)
3. [Activator API](#activator-api)
4. [Utility Functions](#utility-functions)
5. [Pattern Definitions](#pattern-definitions)
6. [Type Reference](#type-reference)

---

## Core Models

### `PatternCategory`

Enum defining pattern categories.

```python
from enum import Enum

class PatternCategory(str, Enum):
    """Pattern categories for organizing trigger patterns."""

    SECURITY = "security"  # Security scanning and analysis
    CONFIG = "config"      # Configuration management
    DEV = "dev"           # Development tasks
    DOCS = "docs"         # Documentation tasks
    PROJECT = "project"   # Project management
```

**Usage:**

```python
from vibesop.triggers.models import PatternCategory

category = PatternCategory.SECURITY
print(category.value)  # "security"
```

---

### `TriggerPattern`

Defines a trigger pattern for intent detection.

```python
from pydantic import BaseModel, Field
from typing import list, Optional

class TriggerPattern(BaseModel):
    """Trigger pattern definition.

    Attributes:
        pattern_id: Unique identifier (format: "category/name")
        name: Human-readable name
        description: Detailed description
        category: Pattern category
        keywords: List of keywords for matching
        regex_patterns: List of regex patterns
        skill_id: Skill to execute
        workflow_id: Workflow to execute (optional, priority over skill)
        priority: Pattern priority (1-100, higher checked first)
        confidence_threshold: Minimum confidence for this pattern
        examples: Example queries that match
        metadata: Additional metadata
    """

    pattern_id: str = Field(..., pattern=r"^[a-z]+/[a-z0-9-]+$")
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    category: PatternCategory

    keywords: list[str] = Field(default_factory=list)
    regex_patterns: list[str] = Field(default_factory=list)

    skill_id: str | None = None
    workflow_id: str | None = None

    priority: int = Field(default=50, ge=1, le=100)
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)

    examples: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

**Example:**

```python
from vibesop.triggers.models import TriggerPattern, PatternCategory

pattern = TriggerPattern(
    pattern_id="security/scan",
    name="Security Scan",
    description="Detects security scanning requests",
    category=PatternCategory.SECURITY,
    keywords=["scan", "security", "vulnerability"],
    regex_patterns=[r"scan.*security", r"security.*scan"],
    skill_id="/security/scan",
    workflow_id="security-review",
    priority=100,
    confidence_threshold=0.6,
    examples=[
        "scan for security vulnerabilities",
        "security scan",
        "扫描安全漏洞"
    ]
)
```

**Validation:**

```python
# Valid pattern_id format
pattern = TriggerPattern(
    pattern_id="security/scan",  # ✅ Valid
    ...
)

# Invalid pattern_id format
pattern = TriggerPattern(
    pattern_id="Security_Scan",  # ❌ Invalid (wrong format)
    ...
)
# ValidationError: pattern_id must match "^[a-z]+/[a-z0-9-]+$"
```

---

### `PatternMatch`

Result of pattern matching operation.

```python
class PatternMatch(BaseModel):
    """Pattern match result.

    Attributes:
        pattern_id: ID of matched pattern
        confidence: Confidence score (0.0 - 1.0)
        metadata: Additional match information
        matched_keywords: Keywords that matched
        matched_regex: Regex patterns that matched
        semantic_score: Semantic similarity score
    """

    pattern_id: str
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    matched_keywords: list[str] = Field(default_factory=list)
    matched_regex: list[str] = Field(default_factory=list)
    semantic_score: float | None = Field(None, ge=0.0, le=1.0)
```

**Example:**

```python
from vibesop.triggers.models import PatternMatch

match = PatternMatch(
    pattern_id="security/scan",
    confidence=0.85,
    metadata={"category": "security", "match_count": 2},
    matched_keywords=["scan", "security"],
    matched_regex=[r"scan.*security"],
    semantic_score=0.78
)

print(f"Matched: {match.pattern_id} with {match.confidence:.2%} confidence")
```

---

## Detector API

### `KeywordDetector`

Main class for detecting user intent from queries.

```python
from vibesop.triggers.detector import KeywordDetector

class KeywordDetector:
    """Detect user intent using keyword patterns.

    Args:
        patterns: List of TriggerPattern to use
        confidence_threshold: Default minimum confidence (0.0-1.0)

    Attributes:
        patterns: Sorted list of patterns (by priority)
        idf_cache: Pre-computed IDF scores
        confidence_threshold: Default confidence threshold
    """

    def __init__(
        self,
        patterns: list[TriggerPattern],
        confidence_threshold: float = 0.6
    ):
        """Initialize detector with patterns."""
        ...
```

#### Methods

##### `detect_best()`

Find the best matching pattern for a query.

```python
def detect_best(
    self,
    query: str,
    min_confidence: float | None = None
) -> PatternMatch | None:
    """Detect the best matching pattern.

    Args:
        query: User input query
        min_confidence: Override default confidence threshold

    Returns:
        PatternMatch if found, None otherwise

    Example:
        >>> detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        >>> match = detector.detect_best("scan for security issues")
        >>> if match:
        ...     print(f"Matched: {match.pattern_id}")
    """
    ...
```

**Usage:**

```python
from vibesop.triggers import KeywordDetector, DEFAULT_PATTERNS

detector = KeywordDetector(patterns=DEFAULT_PATTERNS)

# Basic usage
match = detector.detect_best("scan for security vulnerabilities")

if match:
    print(f"✓ Matched: {match.pattern_id}")
    print(f"  Confidence: {match.confidence:.2%}")
    print(f"  Keywords: {match.matched_keywords}")
else:
    print("✗ No match found")

# Custom confidence threshold
match = detector.detect_best("test", min_confidence=0.4)
```

##### `detect_all()`

Get all matching patterns above threshold.

```python
def detect_all(
    self,
    query: str,
    min_confidence: float | None = None,
    max_results: int = 10
) -> list[PatternMatch]:
    """Detect all matching patterns.

    Args:
        query: User input query
        min_confidence: Override default threshold
        max_results: Maximum number of results

    Returns:
        List of PatternMatch sorted by confidence (descending)

    Example:
        >>> matches = detector.detect_all("scan security")
        >>> for i, match in enumerate(matches, 1):
        ...     print(f"{i}. {match.pattern_id}: {match.confidence:.2%}")
    """
    ...
```

**Usage:**

```python
# Get all matches
matches = detector.detect_all("scan for security issues", min_confidence=0.3)

for i, match in enumerate(matches, 1):
    print(f"{i}. {match.pattern_id}: {match.confidence:.2%}")
    if match.matched_keywords:
        print(f"   Keywords: {', '.join(match.matched_keywords)}")
```

---

## Activator API

### `SkillActivator`

Activates skills and workflows based on pattern matches.

```python
from vibesop.triggers.activator import SkillActivator

class SkillActivator:
    """Activate skills and workflows based on pattern matches.

    Args:
        project_root: Project root directory
        skill_manager: Optional SkillManager instance
        router: Optional SkillRouter instance
        workflow_manager: Optional WorkflowManager instance

    Attributes:
        project_root: Project root path
        skill_manager: SkillManager for skill execution
        router: SkillRouter for semantic routing
        workflow_manager: WorkflowManager for workflow execution
    """

    def __init__(
        self,
        project_root: Path | str = Path("."),
        skill_manager: SkillManager | None = None,
        router: SkillRouter | None = None,
        workflow_manager: WorkflowManager | None = None
    ):
        """Initialize activator."""
        ...
```

#### Methods

##### `activate()`

Activate a skill or workflow based on pattern match.

```python
async def activate(
    self,
    match: PatternMatch,
    input_data: dict[str, Any] | None = None,
    pattern: TriggerPattern | None = None
) -> dict[str, Any]:
    """Activate skill or workflow based on pattern match.

    Args:
        match: Pattern match from KeywordDetector
        input_data: Optional input data for execution
        pattern: Optional TriggerPattern for context

    Returns:
        Execution result dict:
            - success (bool): Whether execution succeeded
            - action (str): "skill", "workflow", or "none"
            - result: Execution result or None
            - error (str | None): Error message if failed
            - pattern_id (str): Matched pattern ID
            - skill_id (str | None): Executed skill ID
            - workflow_id (str | None): Executed workflow ID
            - routed (bool): Whether semantic routing was used

    Example:
        >>> detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
        >>> match = detector.detect_best("scan security")
        >>> activator = SkillActivator()
        >>> result = await activator.activate(match)
        >>> if result["success"]:
        ...     print("Execution successful!")
    """
    ...
```

**Return Value:**

```python
{
    "success": True,  # bool
    "action": "workflow",  # "skill" | "workflow" | "none"
    "result": <execution_result>,  # Any
    "pattern_id": "security/scan",  # str
    "skill_id": None,  # str | None
    "workflow_id": "security-review",  # str | None
    "routed": False,  # bool
    "error": None  # str | None
}
```

**Usage:**

```python
import asyncio
from vibesop.triggers import KeywordDetector, SkillActivator, DEFAULT_PATTERNS

async def execute_query(query: str):
    # Detect intent
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    match = detector.detect_best(query)

    if not match:
        print("❌ No intent detected")
        return

    # Activate skill/workflow
    activator = SkillActivator()
    result = await activator.activate(
        match,
        input_data={"target": "./src"}
    )

    # Check result
    if result["success"]:
        action = result["action"]
        print(f"✓ {action.title()} completed successfully")

        if action == "skill":
            print(f"  Skill: {result['skill_id']}")
        elif action == "workflow":
            print(f"  Workflow: {result['workflow_id']}")
    else:
        print(f"❌ Execution failed: {result['error']}")

# Run
asyncio.run(execute_query("scan for security issues"))
```

---

## Utility Functions

### `auto_activate()`

Convenience function for one-shot detection and activation.

```python
async def auto_activate(
    query: str,
    project_root: Path | str = Path("."),
    min_confidence: float = 0.6,
    input_data: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Convenience function for automatic detection and activation.

    Detects intent from query and automatically activates the appropriate
    skill or workflow.

    Args:
        query: User input query
        project_root: Project root directory
        min_confidence: Minimum confidence threshold
        input_data: Optional input data for execution

    Returns:
        Execution result dict (same as SkillActivator.activate())

    Example:
        >>> result = await auto_activate("scan for security issues")
        >>> print(result["success"])  # True or False
        >>> print(result["action"])  # "skill", "workflow", or "none"

    Raises:
        Nothing (errors are in result dict)
    """
    ...
```

**Usage:**

```python
import asyncio
from vibesop.triggers import auto_activate

# Simple one-shot execution
result = asyncio.run(
    auto_activate(
        query="scan for security issues",
        min_confidence=0.6,
        input_data={"target": "./src"}
    )
)

if result["success"]:
    print("✓ Success!")
else:
    print(f"✗ Failed: {result.get('error')}")
```

---

### Scoring Functions

#### `calculate_keyword_match_score()`

Calculate keyword matching score.

```python
def calculate_keyword_match_score(
    query: str,
    keywords: list[str]
) -> float:
    """Calculate keyword match score (lenient scoring).

    First match gives 0.5 baseline, additional matches add to score.

    Args:
        query: User query
        keywords: List of keywords to match

    Returns:
        Score from 0.0 to 1.0

    Example:
        >>> score = calculate_keyword_match_score("scan security", ["scan", "test"])
        >>> print(score)  # 0.5 (one match)
    """
    ...
```

#### `calculate_regex_match_score()`

Calculate regex pattern matching score.

```python
def calculate_regex_match_score(
    query: str,
    patterns: list[str]
) -> float:
    """Calculate regex match score (lenient scoring).

    Args:
        query: User query
        patterns: List of regex patterns

    Returns:
        Score from 0.0 to 1.0
    """
    ...
```

#### `calculate_semantic_similarity()`

Calculate semantic similarity using TF-IDF.

```python
def calculate_semantic_similarity(
    text1: str,
    text2: str,
    idf_cache: dict[str, float] | None = None
) -> float:
    """Calculate semantic similarity using TF-IDF and cosine similarity.

    Args:
        text1: First text
        text2: Second text
        idf_cache: Optional pre-computed IDF scores

    Returns:
        Similarity score from 0.0 to 1.0
    """
    ...
```

---

## Pattern Definitions

### `DEFAULT_PATTERNS`

List of 30 predefined trigger patterns.

```python
from vibesop.triggers import DEFAULT_PATTERNS

# Access patterns
patterns = DEFAULT_PATTERNS  # List[TriggerPattern]

# Filter by category
security_patterns = [p for p in DEFAULT_PATTERNS if p.category == PatternCategory.SECURITY]

# Find specific pattern
pattern = next((p for p in DEFAULT_PATTERNS if p.pattern_id == "security/scan"), None)
```

**Pattern Categories:**

| Category | Count | Patterns |
|----------|-------|----------|
| Security | 5 | scan, analyze, audit, fix, report |
| Config | 5 | deploy, validate, render, diff, backup |
| Dev | 8 | build, test, debug, refactor, lint, format, install, clean |
| Docs | 6 | generate, update, format, readme, api, changelog |
| Project | 6 | init, migrate, audit, upgrade, clean, status |

---

## Type Reference

### Type Aliases

```python
from pathlib import Path
from typing import Any

# Path type
PathLike = Path | str

# Pattern list
PatternList = list[TriggerPattern]

# Match result (optional)
OptionalMatch = PatternMatch | None

# Execution result
ExecutionResult = dict[str, Any]
```

### Field Validators

```python
# pattern_id validation
pattern_id: str = Field(..., pattern=r"^[a-z]+/[a-z0-9-]+$")
# Must be: "category/name" format
# Examples: "security/scan", "config/deploy", "dev/test"

# priority validation
priority: int = Field(default=50, ge=1, le=100)
# Must be: 1 to 100

# confidence_threshold validation
confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
# Must be: 0.0 to 1.0
```

---

## Error Handling

### Exceptions

```python
# PatternMatch validation error
from pydantic import ValidationError

try:
    match = PatternMatch(
        pattern_id="test",
        confidence=1.5  # Invalid (> 1.0)
    )
except ValidationError as e:
    print(f"Validation error: {e}")

# Detection doesn't raise, returns None
match = detector.detect_best("xyzabc123")
if match is None:
    print("No match found")

# Activation errors are in result dict
result = await activator.activate(match)
if not result["success"]:
    print(f"Error: {result['error']}")
```

---

## Performance Notes

### Detection Performance

```python
# Detector initialization (one-time cost)
detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
# Time: ~8ms

# Detection (very fast)
match = detector.detect_best("scan for security issues")
# Time: ~2.3ms
# Throughput: ~427 queries/second
```

### Memory Usage

```python
# Detector instance: ~4KB
# IDF cache: ~5KB
# Total per detector: ~10KB

# Reuse detector instances
detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
for query in queries:
    detector.detect_best(query)  # Fast, no re-initialization
```

---

## Best Practices

### 1. Reuse Detector Instances

```python
# ❌ Bad: Creates new detector each time
for query in queries:
    detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
    match = detector.detect_best(query)

# ✅ Good: Reuse detector
detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
for query in queries:
    match = detector.detect_best(query)
```

### 2. Handle None Results

```python
match = detector.detect_best(query)

# ❌ Bad: Assumes match exists
print(match.pattern_id)  # AttributeError if match is None

# ✅ Good: Check for None
if match:
    print(match.pattern_id)
else:
    print("No match found")
```

### 3. Use Async for Activation

```python
# ❌ Bad: Blocking call
result = asyncio.run(activator.activate(match))

# ✅ Good: Proper async
async def process():
    result = await activator.activate(match)
    return result

result = asyncio.run(process())
```

### 4. Validate Input Data

```python
# ❌ Bad: No validation
result = await activator.activate(match, input_data=user_input)

# ✅ Good: Validate input
import json
from typing import TypedDict

class InputData(TypedDict):
    target: str
    severity: str

def validate_input(data: str) -> InputData:
    return json.loads(data)

validated = validate_input(user_input)
result = await activator.activate(match, input_data=validated)
```

---

## Migration Guide

### From v1.0 to v2.0

**v1.0 (Manual skill selection):**

```python
from vibesop.core.skills.manager import SkillManager

manager = SkillManager()
result = await manager.execute_skill("/security/scan", query="...")
```

**v2.0 (Automatic intent detection):**

```python
from vibesop.triggers import auto_activate

result = await auto_activate("scan for security issues")
# Automatically detects and activates the right skill
```

**Benefits:**
- ✅ Natural language queries
- ✅ Automatic skill selection
- ✅ Fallback to semantic routing
- ✅ Bilingual support

---

*Last updated: 2026-04-04*
