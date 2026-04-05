# VibeSOP v3.0 Migration Guide

This guide helps you migrate from VibeSOP v2.x to v3.0.

## Overview of Changes

v3.0 is a **major refactor** that consolidates duplicate abstractions and provides a unified interface. The key changes are:

1. **Unified Routing**: Single `UnifiedRouter` replaces multiple routing components
2. **Matching Infrastructure**: Consolidated in `vibesop.core.matching`
3. **Configuration**: Multi-source `ConfigManager` replaces scattered config files
4. **CLI**: `vibe route` replaces `vibe auto`

## Breaking Changes

### CLI Commands

| Old Command | New Command | Notes |
|-------------|-------------|-------|
| `vibe auto "query"` | `vibe route "query"` | Unified routing interface |
| `vibe route-select` | `vibe route --top 5` | Use `--top` option |
| `vibe route-validate` | `vibe route --validate` | Coming soon |

### Python API

#### Triggers Module (DEPRECATED)

```python
# ❌ Old (v2.x)
from vibesop.triggers import KeywordDetector, DEFAULT_PATTERNS
detector = KeywordDetector(patterns=DEFAULT_PATTERNS)
match = detector.detect_best("query")

# ✅ New (v3.0)
from vibesop.core.matching import KeywordMatcher
matcher = KeywordMatcher()
results = matcher.match("query", candidates)
```

#### Routing Module

```python
# ❌ Old (v2.x)
from vibesop.core.routing.engine import SkillRouter
from vibesop.core.models import RoutingRequest

router = SkillRouter()
request = RoutingRequest(query="query")
result = router.route(request)

# ✅ New (v3.0)
from vibesop.core.routing import UnifiedRouter

router = UnifiedRouter()
result = router.route("query")
```

#### Semantic Matching

```python
# ❌ Old (v2.x)
from vibesop.semantic import SemanticMatcher

matcher = SemanticMatcher()
result = matcher.match(query, skills)

# ✅ New (v3.0)
from vibesop.core.matching import EmbeddingMatcher

matcher = EmbeddingMatcher()  # Requires sentence-transformers
results = matcher.match(query, candidates)
```

## Configuration Changes

### Old Configuration Files (v2.x)

```
core/policies/skill-selection.yaml  # ❌ Removed
core/policies/task-routing.yaml      # ❌ Removed
.vibe/skill-routing.yaml             # ❌ Removed
.vibe/preferences.json               # ⚠️  Legacy support
```

### New Configuration (v3.0)

```yaml
# ~/.vibe/config.yaml (global) or .vibe/config.yaml (project)
routing:
  min_confidence: 0.3
  auto_select_threshold: 0.6
  enable_embedding: false  # Requires sentence-transformers
  max_candidates: 3
  use_cache: true

security:
  scan_external: true
  require_audit: true
  allowed_paths:
    - ~/.claude/skills
    - ~/.config/skills
    - .vibe/skills

semantic:
  enabled: false
  model: "paraphrase-multilingual-MiniLM-L12-v2"
  cache_embeddings: true
```

### Programmatic Configuration

```python
# Old (v2.x)
from vibesop.core.config import ConfigLoader

loader = ConfigLoader()
config = loader.load_routing_config()

# New (v3.0)
from vibesop.core.config import ConfigManager, RoutingConfig

# Auto-load from files
manager = ConfigManager()
config = manager.get_routing_config()

# Or create programmatically
config = RoutingConfig(
    min_confidence=0.2,
    enable_embedding=False,
)
router = UnifiedRouter(config=config)
```

## Skill Definition Changes

### Old Format (v2.x)

```yaml
# core/skills/debug/SKILL.md
---
id: systematic-debugging
name: Debugging Skill
triggers:
  - debug
  - error
  - bug
---
```

### New Format (v3.0)

```yaml
# core/skills/systematic-debugging/SKILL.md
---
name: systematic-debugging
description: Systematic debugging - find root cause before fixing
namespace: builtin
tags:
  - debug
  - error
  - troubleshooting
---
```

## Step-by-Step Migration

### 1. Update CLI Usage

```bash
# Find all usages of old commands
grep -r "vibe auto" . --include="*.sh" --include="*.md"

# Replace with new commands
# vibe auto "..." → vibe route "..."
```

### 2. Update Python Code

```python
# Find imports to update
# - from vibesop.triggers import
# - from vibesop.core.routing.engine import
# - from vibesop.semantic import

# Update imports
# from vibesop.triggers import KeywordDetector
# → from vibesop.core.matching import KeywordMatcher

# from vibesop.core.routing.engine import SkillRouter
# → from vibesop.core.routing import UnifiedRouter
```

### 3. Update Configuration Files

```bash
# Migrate old config to new format
# 1. Review ~/.vibe/preferences.json
# 2. Create ~/.vibe/config.yaml with equivalent settings
# 3. Delete old config files (optional)
```

### 4. Update Custom Skills

```bash
# Review SKILL.md files
# - Update frontmatter to include namespace and tags
# - Ensure description is clear and concise
```

## Common Migration Patterns

### Pattern 1: Simple Keyword Detection

```python
# Old
detector = KeywordDetector()
if detector.detect("debug"):
    # handle debug

# New
matcher = KeywordMatcher()
results = matcher.match("debug", candidates)
if results and results[0].confidence > 0.5:
    # handle match
```

### Pattern 2: Route and Execute

```python
# Old
router = SkillRouter()
result = router.route(RoutingRequest(query="debug"))
skill = SkillLoader().load(result.primary.skill_id)
skill.execute()

# New
router = UnifiedRouter()
result = router.route("debug")
if result.has_match:
    skill_id = result.primary.skill_id
    # Load and execute skill
```

### Pattern 3: Custom Matching

```python
# Old
from vibesop.triggers.utils import cosine_similarity
score = cosine_similarity(vec1, vec2)

# New
from vibesop.core.matching import SimilarityCalculator
calc = SimilarityCalculator(metric=SimilarityMetric.COSINE)
score = calc.calculate_single(vec1, vec2)
```

## Testing Your Migration

```bash
# Test basic routing
vibe route "debug this error"
vibe route "help me plan"

# Test with options
vibe route "test" --min-confidence 0.2 --json

# Run tests
uv run pytest tests/

# Check for deprecated imports
python -W default::DeprecationWarning your_script.py
```

## Getting Help

- **Issues**: https://github.com/nehcuh/vibesop-py/issues
- **Discussions**: https://github.com/nehcuh/vibesop-py/discussions
- **Documentation**: See README.md and docs/

## Rollback Plan

If you need to rollback to v2.x:

```bash
# Uninstall v3.0
pip uninstall vibesop

# Install v2.x
pip install vibesop==2.1.0
```

## Deprecation Timeline

| Version | Status |
|---------|--------|
| v3.0.0 | Current - `vibesop.triggers` deprecated |
| v3.5.0 | Warnings become errors |
| v4.0.0 | Deprecated modules removed |

## New Features in v3.0

### External Skill Loading

v3.0 supports loading skills from external directories:

```python
from vibesop.core.skills import ExternalSkillLoader

loader = ExternalSkillLoader()
skills = loader.discover_all()

# Skills are loaded from:
# - ~/.claude/skills/
# - ~/.config/skills/
# - ~/.vibe/skills/
```

### Security Auditing

All external skills are automatically audited:

```python
from vibesop.security import SkillSecurityAuditor

auditor = SkillSecurityAuditor()
result = auditor.audit_skill_file(path/to/skill.md)

if result.is_safe:
    print("Safe to load")
else:
    print(f"Blocked: {result.reason}")
    for threat in result.threats:
        print(f"  - {threat.name}: {threat.description}")
```

**Protected Against**:
- Prompt injection ("ignore all instructions")
- Role hijacking ("you are now admin")
- Command injection (`<|system.exec()`)
- Instruction override
- Privilege escalation
- Data exfiltration attempts
