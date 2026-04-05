# VibeSOP - Python Edition

> **Production-Grade AI-Assisted Development Workflow SOP**
> **v3.0.0** - Unified architecture with consolidated matching and routing

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/badge/Ruff-Enabled-black.svg)](https://github.com/astral-sh/ruff)
[![Pyright](https://img.shields.io/badge/Pyright-Strict-blue.svg)](https://github.com/microsoft/pyright)
[![Version](https://img.shields.io/badge/Version-3.0.0-green.svg)](https://github.com/nehcuh/vibesop-py)

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/nehcuh/vibesop-py.git && cd vibesop-py

# Using uv (recommended)
uv sync

# Run CLI
vibe --help
```

## ✨ What's New in v3.0.0

### 🏗️ Unified Architecture

**v3.0** is a major refactor that consolidates duplicate abstractions and provides a clean, unified interface:

- **UnifiedRouter**: Single entry point for all routing operations
- **Matching Infrastructure**: Consolidated tokenization, similarity, and TF-IDF
- **ConfigManager**: Multi-source configuration with clear priority
- **Deprecated**: `vibesop.triggers` (use `vibesop.core.matching` instead)

### 🔀 Unified Routing

```bash
# One command for all routing (replaces vibe auto)
vibe route "debug this error"

# With options
vibe route "help me plan" --min-confidence 0.2
vibe route "review code" --json

# Chinese support
vibe route "扫描安全漏洞"
```

**Routing Layers** (tried in priority order):
1. **Keyword** (<1ms): Fast keyword matching
2. **TF-IDF** (~5ms): Semantic similarity
3. **Embedding** (~20ms): Vector matching (optional)
4. **Levenshtein** (~10ms): Fuzzy matching fallback

## 📚 Core Concepts

### Principles

VibeSOP is built on these principles:

1. **Production-First**: Every feature is validated in real projects
2. **Structure > Prompting**: Configuration over prompt engineering
3. **Memory > Intelligence**: Record solutions, avoid repeating mistakes
4. **Verification > Confidence**: Don't claim done without proof
5. **Portable > Specific**: Core is portable, adapters for platforms

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      UnifiedRouter                          │
│  (Single entry point for all routing operations)            │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Keyword   │  │   TF-IDF    │  │   Embedding (opt)   │  │
│  │   Matcher   │  │   Matcher   │  │     Matcher         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│              Matching Infrastructure                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Tokenizers  │  │ Similarity  │  │      TF-IDF         │  │
│  │  (CJK, etc) │  │  (Cosine)   │  │   Calculator        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                   ConfigManager                             │
│  (defaults → global → project → env → cli)                 │
└─────────────────────────────────────────────────────────────┘
```

## 🛠️ Usage

### Basic Routing

```bash
# Find the best skill for your query
vibe route "help me debug this error"

# Show more alternatives
vibe route "deploy" --top 5

# Lower confidence threshold
vibe route "test" --min-confidence 0.2

# JSON output
vibe route "review" --json
```

### Configuration

Configuration is loaded from multiple sources (priority order):

1. **Built-in defaults**: `vibesop/core/config/manager.py`
2. **Global config**: `~/.vibe/config.yaml`
3. **Project config**: `.vibe/config.yaml`
4. **Environment**: `VIBE_ROUTING_MIN_CONFIDENCE=0.2`
5. **CLI**: `--min-confidence 0.2`

Example `~/.vibe/config.yaml`:

```yaml
routing:
  min_confidence: 0.3
  enable_embedding: false
  use_cache: true

security:
  scan_external: true
  require_audit: true

semantic:
  enabled: false
  model: "paraphrase-multilingual-MiniLM-L12-v2"
```

### Skills

Skills are discovered from:
- Built-in: `core/skills/`
- Project: `.vibe/skills/`
- External: `~/.claude/skills/`, `~/.config/skills/`

```bash
# List available skills
vibe skills list

# Show skill details
vibe skills show systematic-debugging
```

### Security

External skills are automatically audited before loading:

```python
from vibesop.security import SkillSecurityAuditor

auditor = SkillSecurityAuditor()
result = auditor.audit_skill_file(path/to/skill.md)

if result.is_safe:
    print("Safe to load")
else:
    print(f"Blocked: {result.reason}")
```

**Threat Detection**:
- Prompt injection ("ignore all instructions")
- Role hijacking ("you are now admin")
- Command injection (`<|system.exec()`)
- Instruction override
- Privilege escalation
- Data exfiltration attempts

## 🧩 Development

### Project Structure

```
src/vibesop/
├── core/
│   ├── matching/        # Unified matching infrastructure
│   │   ├── base.py      # Protocols and models
│   │   ├── tokenizers.py
│   │   ├── similarity.py
│   │   ├── tfidf.py
│   │   └── strategies.py
│   ├── routing/
│   │   └── unified.py   # UnifiedRouter
│   ├── config/
│   │   └── manager.py   # ConfigManager
│   └── skills/          # Skill management
├── cli/                 # CLI commands
└── adapters/            # Platform adapters
```

### Testing

```bash
# Run all tests
uv run pytest

# Run specific test
uv run pytest tests/unit/matching/test_matchers.py

# With coverage
uv run pytest --cov=vibesop --cov-report=html
```

## 📖 Migration Guide (v2.x → v3.0)

### Breaking Changes

| v2.x | v3.0 |
|------|------|
| `vibe auto "query"` | `vibe route "query"` |
| `from vibesop.triggers` | `from vibesop.core.matching` |
| `KeywordDetector` | `KeywordMatcher` |
| `SkillRouter` | `UnifiedRouter` |

### Code Migration

```python
# Old (v2.x)
from vibesop.triggers import KeywordDetector
from vibesop.core.routing.engine import SkillRouter

detector = KeywordDetector()
router = SkillRouter()

# New (v3.0)
from vibesop.core.matching import KeywordMatcher
from vibesop.core.routing import UnifiedRouter

matcher = KeywordMatcher()
router = UnifiedRouter()
result = router.route("query")
```

### Deprecated Modules

- `vibesop.triggers` → Use `vibesop.core.matching`
- `vibesop.semantic` → Use `vibesop.core.matching.EmbeddingMatcher`

These will be removed in v4.0.0.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines and submit PRs.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a PR

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- Original VibeSOP concept and Ruby implementation
- Inspiration from [obra/superpowers](https://github.com/obra/superpowers)
- Inspiration from [garrytan/gstack](https://github.com/garrytan/gstack)
