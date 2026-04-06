# Cold Start Strategy

> **Version**: 4.0.0
> **Last Updated**: 2026-04-06

## Overview

VibeSOP's routing improves over time through preference learning. But what happens on the first run, or when there's no historical data?

This document describes VibeSOP's **cold start strategy** — how it routes queries effectively without any prior learning.

## What is Cold Start?

**Cold start** = First few routing calls when:
- VibeSOP is newly installed
- No preference history exists
- Query patterns haven't been seen before

## Cold Start Strategy

### 1. Built-in Query Mappings

VibeSOP includes pre-configured mappings for common queries:

| Query Pattern | Default Skill | Keywords |
|---------------|---------------|----------|
| `debug`, `bug`, `error` | `systematic-debugging` | debug, 调试, bug, error |
| `review`, `代码审查` | `gstack/review` | review, 审查 |
| `deploy`, `部署` | `gstack/ship` | deploy, 部署, release |
| `test`, `测试` | `superpowers/tdd` | test, 测试, tdd |
| `brainstorm`, `头脑风暴` | `superpowers/brainstorm` | brainstorm, 头脑风暴 |
| `architect`, `架构` | `superpowers/architect` | architect, 架构, design |
| `plan`, `计划` | `riper-workflow` | plan, 计划, planning |
| `optimize`, `优化` | `superpowers/optimize` | optimize, 优化, performance |
| `refactor`, `重构` | `superpowers/refactor` | refactor, 重构, clean up |

These mappings provide sensible defaults for 90%+ of common queries.

### 2. Default Matcher Weights

When no historical data exists, matchers use default confidence weights:

| Matcher | Default Weight | Rationale |
|---------|---------------|-----------|
| Keyword | 1.0 | Exact matches are reliable |
| Scenario | 0.95 | Predefined patterns are high-quality |
| TF-IDF | 0.85 | Semantic similarity works well |
| Embedding | 0.90 | Vector matching is accurate |
| Levenshtein | 0.70 | Fallback, lower confidence |

### 3. P0 Skills Always Included

Core skills are always in the candidate set:
- `systematic-debugging`
- `verification-before-completion`
- `session-end`

### 4. Namespace Priority

When queries are ambiguous, namespaces are prioritized:

| Namespace | Priority | Rationale |
|-----------|----------|-----------|
| `builtin` | 100 | Core, most tested |
| `superpowers` | 80 | General-purpose, high quality |
| `gstack` | 70 | Engineering-focused |
| `omx` | 60 | Specialized workflows |

## Performance Characteristics

### Cold Start vs. Warm

| Metric | Cold Start | Warm (after learning) |
|--------|------------|----------------------|
| Accuracy | ~75% | ~90%+ |
| Avg Latency | 0.1ms | 0.08ms |
| First Call | ~250ms* | ~0.1ms** |

*First call loads skill cache
*Subsequent calls use cached candidates

### Learning Timeline

- **0-10 queries**: Using built-in mappings only
- **10-50 queries**: Preference learning starts influencing
- **50+ queries**: Personalized routing is primary driver

## Programmatic Usage

### Using Cold Start Strategy

```python
from vibesop.core.optimization import get_cold_start_strategy

strategy = get_cold_start_strategy(".")

# Get built-in mapping for a query
mapping = strategy.get_mapping_for_query("debug this error")
if mapping:
    print(f"Default skill: {mapping.skill_id}")

# Get default matcher weights
weights = strategy.get_default_weights()

# Check if cache warming is recommended
if strategy.should_warm_cache():
    router = UnifiedRouter()
    router.route("warmup")  # Load cache
```

### Customizing Cold Start

```python
from vibesop.core.optimization.cold_start import ColdStartStrategy

class CustomColdStart(ColdStartStrategy):
    def get_builtin_mappings(self):
        # Add custom mappings
        base = super().get_builtin_mappings()
        base.append(QuerySkillMapping(
            pattern="ci/cd",
            skill_id="my-pipeline-skill",
            keywords=["pipeline", "ci", "cd"]
        ))
        return base
```

## Configuration

Cold start behavior is configured via:

```yaml
# .vibe/config.yaml
routing:
  # Enable/disable built-in mappings
  use_builtin_mappings: true

  # Minimum samples before preference learning kicks in
  preference_min_samples: 3

  # Cache candidates for performance
  use_cache: true
```

## Troubleshooting

### Issue: First route() call is slow

**Cause**: Cache not loaded, scanning all skill directories

**Solution**: Warm the cache:
```python
router = UnifiedRouter()
router.route("warmup")  # Loads cache
```

### Issue: Wrong skill selected on first try

**Cause**: Cold start using default mappings

**Solution**:
1. Check built-in mappings match your expectations
2. After a few queries, preference learning will improve accuracy
3. Use explicit override: `/review my code`

### Issue: Custom skill not being discovered

**Cause**: Skill not in built-in mappings

**Solution**:
1. Ensure SKILL.md has good intent keywords
2. Use explicit override initially
3. Preference learning will pick it up after use

## Best Practices

1. **For New Installations**:
   - Let VibeSOP learn your patterns over 10-20 queries
   - Use explicit overrides (`/skill`) for critical tasks
   - Trust the built-in mappings for common queries

2. **For Custom Skills**:
   - Include clear intent keywords in SKILL.md
   - Test with explicit override first
   - Preference learning will adapt after a few uses

3. **For Teams**:
   - Share preference files (`~/.vibe/preferences.json`)
   - Customize built-in mappings via code
   - Document team-specific routing patterns

---

*For optimization details, see [architecture/routing-system.md](architecture/routing-system.md)*
*For preference learning, see [core/optimization/preference_boost.py](../src/vibesop/core/optimization/preference_boost.py)*
