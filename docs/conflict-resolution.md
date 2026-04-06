# Conflict Resolution Framework

> **Version**: 4.0.0
> **Last Updated**: 2026-04-06

## Overview

When multiple skills match a user query, VibeSOP needs a strategy to choose the best one. The **Conflict Resolution Framework** provides a flexible, configurable approach to this problem.

## The Problem

```
User Query: "review my code"

Matches:
  - gstack/review (confidence: 0.85)
  - superpowers/refactor (confidence: 0.82)
  - builtin/verification (confidence: 0.78)

Which one should be selected?
```

## Resolution Strategies

VibeSOP uses multiple strategies, tried in priority order:

### 1. Explicit Override (Priority: 100)

**When**: User explicitly specifies a skill

**Patterns**:
- `/review` → Use `gstack/review`
- `use tdd` → Use `superpowers/tdd`
- `run review` → Use `gstack/review`

**Code**: `ExplicitOverrideStrategy`

### 2. Confidence Gap (Priority: 90)

**When**: One skill has significantly higher confidence

**Logic**: If top confidence - second confidence > threshold (default 0.15)

**Example**:
```
gstack/review: 0.90
superpowers/refactor: 0.65  # Gap: 0.25 > 0.15 → Select gstack/review
```

**Code**: `ConfidenceGapStrategy`

### 3. Namespace Priority (Priority: 80)

**When**: Skills have similar confidence

**Default Priorities**:
| Namespace | Priority |
|-----------|----------|
| builtin | 100 |
| superpowers | 80 |
| gstack | 70 |
| omx | 60 |

**Example**:
```
builtin/debug: 0.75
gstack/investigate: 0.75  # Same confidence, builtin wins
```

**Code**: `NamespacePriorityStrategy`

### 4. Recency (Priority: 70)

**When**: User recently used a skill for similar queries

**Logic**: If a skill was used in the last 7 days, prefer it

**Example**:
```
# User used gstack/review 2 hours ago
gstack/review: 0.75 (recent: ✓)
superpowers/refactor: 0.78 (recent: ✗) → gstack/review still wins
```

**Code**: `RecencyStrategy`

### 5. Fallback (Priority: 0)

**When**: No other strategy applies

**Logic**: Select highest confidence skill

**Code**: `FallbackStrategy`

## Using the Framework

### Basic Usage

```python
from vibesop.core.routing import ConflictResolver
from vibesop.core.matching import MatchResult

resolver = ConflictResolver()

matches = [
    MatchResult(skill_id="gstack/review", confidence=0.85, ...),
    MatchResult(skill_id="superpowers/refactor", confidence=0.82, ...),
]

resolution = resolver.resolve(matches, "review my code")

print(f"Primary: {resolution.primary}")
print(f"Reason: {resolution.reason}")
print(f"Needs Review: {resolution.needs_review}")
```

### Custom Strategies

```python
from vibesop.core.routing import ResolutionStrategy, ConflictResolver

class CustomStrategy(ResolutionStrategy):
    def resolve(self, matches, query, context=None):
        # Your custom logic here
        return ConflictResolution(
            primary=best_match.skill_id,
            alternatives=[...],
            reason="Custom reason",
        )

    def priority(self):
        return 85  # Between ConfidenceGap and NamespacePriority

resolver = ConflictResolver()
resolver.add_strategy(CustomStrategy())
```

### Customizing Namespace Priorities

```python
from vibesop.core.routing import NamespacePriorityStrategy

custom_priorities = {
    "my-company-skills": 95,  # Higher than builtin
    "builtin": 90,
    "superpowers": 70,
}

strategy = NamespacePriorityStrategy(priorities=custom_priorities)
```

## Configuration

Conflict resolution can be configured via YAML:

```yaml
# .vibe/config.yaml
conflict_resolution:
  # Enable/disable strategies
  strategies:
    explicit_override: true
    confidence_gap: true
    namespace_priority: true
    recency: true

  # Strategy parameters
  confidence_gap_threshold: 0.15  # Minimum gap for auto-select
  recency_days: 7                  # Days to consider "recent"

  # Namespace priorities (override defaults)
  namespace_priorities:
    builtin: 100
    superpowers: 80
    gstack: 70
    omx: 60
```

## Resolution Metadata

Each `ConflictResolution` includes metadata:

```python
{
    "primary": "gstack/review",
    "alternatives": ["superpowers/refactor"],
    "reason": "Clear confidence gap: ...",
    "needs_review": False,
    "metadata": {
        "gap": 0.25,
        "strategy": "confidence_gap"
    }
}
```

## Best Practices

1. **For Custom Skills**:
   - Give your namespace a clear priority
   - Use descriptive intent keywords in SKILL.md

2. **For Teams**:
   - Agree on namespace priorities
   - Share conflict resolution config via `.vibe/config.yaml`

3. **For Debugging**:
   - Check `resolution.metadata["strategy"]` to see which strategy was used
   - Enable `needs_review` logging for close calls

## Examples

### Example 1: Clear Winner

```
Matches:
  gstack/review: 0.90
  superpowers/refactor: 0.60

Result: gstack/review
Reason: Confidence gap: 0.30 > 0.15
Strategy: confidence_gap
```

### Example 2: Namespace Priority

```
Matches:
  builtin/debug: 0.75
  gstack/investigate: 0.75

Result: builtin/debug
Reason: Namespace priority: builtin (100) > gstack (70)
Strategy: namespace_priority
```

### Example 3: Recent Usage

```
Matches:
  gstack/review: 0.75 (used 2 hours ago)
  superpowers/refactor: 0.78

Result: gstack/review
Reason: Recently used: gstack/review (used 2h ago)
Strategy: recency
```

### Example 4: Close Call (Needs Review)

```
Matches:
  gstack/review: 0.82
  superpowers/refactor: 0.80

Result: gstack/review
Reason: Highest confidence: 0.82
Needs Review: true (gap < 0.10)
Strategy: fallback
```

## Extending

### Adding a New Strategy

1. Create a class extending `ResolutionStrategy`
2. Implement `resolve()` and `priority()` methods
3. Add to resolver via `add_strategy()`

```python
class MyStrategy(ResolutionStrategy):
    def resolve(self, matches, query, context=None):
        # Return ConflictResolution or None
        pass

    def priority(self):
        return 75  # Your priority
```

---

*For routing details, see [architecture/routing-system.md](architecture/routing-system.md)*
*For cold start behavior, see [cold-start-guide.md](cold-start-guide.md)*
